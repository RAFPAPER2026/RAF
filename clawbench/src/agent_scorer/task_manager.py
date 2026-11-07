"""AgentTaskManager — 单任务生命周期/超时（模块单例）。"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.agent_scorer.exceptions import AgentConcurrentError
from src.agent_scorer.models import AgentEvalStatus, AgentEvalTask
from src.agent_scorer.scorer import AgentScorer

DEFAULT_TIMEOUT_SECONDS = 300


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentTaskManager:
    """单任务评测管理器。任务 key：`{model_id}::{task_name}::{run_id}`（run_id 防止跨 run 冲突）。

    执行调度：优先复用当前运行中的事件循环（async 上下文）；否则起一个守护线程
    常驻事件循环（FastAPI 同步路由在 anyio worker 线程中调用，无 running loop）。
    """

    def __init__(
        self,
        agent_config_path: str | Path | None = None,
        scorer_factory: Any = None,
    ):
        self.agent_config_path = Path(agent_config_path) if agent_config_path else None
        self._scorer_factory = scorer_factory or (lambda: AgentScorer(self.agent_config_path))
        self._tasks: dict[str, AgentEvalTask] = {}
        self._async_handles: dict[str, asyncio.Task] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """返回可用的事件循环（运行中或新建守护线程常驻）。"""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                threading.Thread(target=loop.run_forever, daemon=True).start()
                self._loop = loop
        return self._loop

    @staticmethod
    def task_key(model_id: str, task_name: str, run_id: str) -> str:
        return f"{model_id}::{task_name}::{run_id}"

    def get_task(self, key: str) -> Optional[AgentEvalTask]:
        return self._tasks.get(key)

    def _timeout_seconds(self) -> float:
        """超时取 agent 配置（单任务默认 300s）。"""
        timeout = DEFAULT_TIMEOUT_SECONDS
        if self.agent_config_path and self.agent_config_path.is_file():
            try:
                cfg = json.loads(self.agent_config_path.read_text(encoding="utf-8"))
                if isinstance(cfg, dict) and cfg.get("timeout_seconds"):
                    timeout = float(cfg["timeout_seconds"])
            except (OSError, ValueError, TypeError):
                pass
        return timeout

    def start_eval(
        self,
        *,
        model_id: str,
        task_name: str,
        run_id: str,
        config: Any,
        task_dir: str | Path,
        result_dir: str | Path,
        evaluate_trace: bool = False,
    ) -> AgentEvalTask:
        """已有 RUNNING 任务 → `AgentConcurrentError`（API 层 409）；
        在常驻事件循环上调度 `_run()`。
        """
        key = self.task_key(model_id, task_name, run_id)
        existing = self._tasks.get(key)
        if existing is not None and existing.status == AgentEvalStatus.RUNNING:
            raise AgentConcurrentError(f"任务 {key} 已有运行中的评测")
        task = AgentEvalTask(
            task_key=key,
            model_id=model_id,
            task_name=task_name,
            run_id=run_id,
            status=AgentEvalStatus.RUNNING,
            started_at=_now_iso(),
        )
        self._tasks[key] = task
        timeout = self._timeout_seconds()
        loop = self._ensure_loop()

        async def _run() -> None:
            self._async_handles[key] = asyncio.current_task()
            try:
                scorer = self._scorer_factory()
                coro = scorer.evaluate(config, evaluate_trace, task_dir, result_dir)
                await self._run_with_timeout(task, key, coro, timeout)
            finally:
                self._async_handles.pop(key, None)

        loop.call_soon_threadsafe(lambda: loop.create_task(_run()))
        return task

    async def _run_with_timeout(
        self, task: AgentEvalTask, key: str, coro: Any, timeout: float
    ) -> None:
        """`asyncio.wait_for`；成功→COMPLETED；超时→TIMEOUT「Evaluation timed out after {n}s」；
        `AgentConcurrentError` 重抛不标记；其他异常→FAILED+str(e)；finally 移出 `_async_handles`。
        """
        try:
            await asyncio.wait_for(coro, timeout=timeout)
            task.status = AgentEvalStatus.COMPLETED
        except asyncio.TimeoutError:
            task.status = AgentEvalStatus.TIMEOUT
            task.error = f"Evaluation timed out after {timeout}s"
        except AgentConcurrentError:
            raise
        except Exception as exc:  # noqa: BLE001 - 评测异常统一标记 FAILED
            task.status = AgentEvalStatus.FAILED
            task.error = str(exc)
        finally:
            task.finished_at = _now_iso()

    def cancel_eval(self, key: str) -> Optional[AgentEvalTask]:
        """取消常驻循环上的任务，标 FAILED「Cancelled by user」。"""
        task = self._tasks.get(key)
        handle = self._async_handles.get(key)
        if handle is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(handle.cancel)
            self._async_handles.pop(key, None)
        if task is not None and task.status == AgentEvalStatus.RUNNING:
            task.status = AgentEvalStatus.FAILED
            task.error = "Cancelled by user"
            task.finished_at = _now_iso()
        return task

    def clear_completed(self, key: str) -> None:
        """删 COMPLETED/FAILED/TIMEOUT（允许重试）。"""
        task = self._tasks.get(key)
        if task is not None and task.status in (
            AgentEvalStatus.COMPLETED,
            AgentEvalStatus.FAILED,
            AgentEvalStatus.TIMEOUT,
        ):
            self._tasks.pop(key, None)


_agent_manager: Optional[AgentTaskManager] = None


def init_agent_manager(
    agent_config_path: str | Path | None = None, scorer_factory: Any = None
) -> AgentTaskManager:
    global _agent_manager
    _agent_manager = AgentTaskManager(agent_config_path, scorer_factory)
    return _agent_manager


def get_agent_manager() -> AgentTaskManager:
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentTaskManager()
    return _agent_manager
