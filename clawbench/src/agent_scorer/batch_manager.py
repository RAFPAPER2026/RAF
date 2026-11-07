"""BatchEvalManager — 批量编排。

并发模型：`worker_count = max(1, min(concurrency, len(tasks)))` 固定 worker 池从共享
`asyncio.Queue` 取任务——**结构性并发，无 `asyncio.Semaphore`**（修复过 concurrency=1
原地重试重入信号量死锁）；空闲槽立即回填。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.agent_scorer.batch_models import BatchEvalSession, BatchTask, BatchTaskStatus
from src.agent_scorer.exceptions import AgentConcurrentError
from src.agent_scorer.models import AgentEvalStatus, AgentReview
from src.agent_scorer.scorer import AgentScorer
from src.models import TaskConfig
from src.agent_scorer.task_manager import AgentTaskManager
from src.rubric.compat import detect_rubric_format
from src.rubric.models import QueryRubric
from src.rubric.scoring import compute_rubric_score
from src.runs import resolve_run_dir

MAX_ATTEMPTS = 2  # 原地重试一次，期间保持 RUNNING 避免 UI 闪烁
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_CONCURRENCY = 32


def _now() -> datetime:
    return datetime.now()


class BatchEvalManager:
    """批量评测编排器。`loader` 可选（采纳时写 manual_score/trace_quality），
    `agent_manager` 可选（单任务 RUNNING 状态互斥检查）。
    """

    def __init__(
        self,
        result_base_dir: str | Path,
        tasks_dir: str | Path | None = None,
        agent_config_path: str | Path | None = None,
        loader: Any = None,
        agent_manager: Optional[AgentTaskManager] = None,
        scorer_factory: Any = None,
    ):
        self.result_base_dir = Path(result_base_dir)
        self.tasks_dir = Path(tasks_dir) if tasks_dir else None
        self.agent_config_path = Path(agent_config_path) if agent_config_path else None
        self._scorer_factory = scorer_factory or (lambda: AgentScorer(self.agent_config_path))
        self.loader = loader
        self.agent_manager = agent_manager
        self._sessions: dict[str, BatchEvalSession] = {}

    def _timeout_seconds(self) -> float:
        """批量取 agent 配置 timeout_seconds（当前 1800）。"""
        timeout = DEFAULT_TIMEOUT_SECONDS
        if self.agent_config_path and self.agent_config_path.is_file():
            try:
                cfg = json.loads(self.agent_config_path.read_text(encoding="utf-8"))
                if isinstance(cfg, dict) and cfg.get("timeout_seconds"):
                    timeout = float(cfg["timeout_seconds"])
            except (OSError, ValueError, TypeError):
                pass
        return timeout

    # ------------------------------------------------------------ 会话

    def get_session(self, batch_id: str) -> Optional[BatchEvalSession]:
        return self._sessions.get(batch_id)

    def latest_session(self, model_id: str) -> Optional[BatchEvalSession]:
        """每模型最新批次（前端重开弹窗用）。"""
        sessions = [
            s for s in self._sessions.values()
            if s.tasks and s.tasks[0].model_id == model_id
        ]
        return max(sessions, key=lambda s: s.started_at or "") if sessions else None

    # ------------------------------------------------------------ 资格过滤

    def _check_eligibility(
        self, model_id: str, task_name: str, run_id: str, skip_existing: bool
    ) -> tuple[bool, Optional[BatchTask], str]:
        """资格过滤：verifier_type=="manual"、tree rubric、run 可解析且 score.json 存在、
        非 RUNNING、（skip_existing=True 时）score.json 无 agent_review。
        """
        if self.tasks_dir is None:
            return False, None, "tasks_dir 未配置"
        config_path = TaskConfig.config_path(self.tasks_dir / task_name)
        if not config_path.is_file():
            return False, None, f"任务配置缺失：{task_name}"
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False, None, "config.json 解析失败"
        if not isinstance(raw, dict):
            return False, None, "config.json 内容异常"
        if raw.get("verifier_type") != "manual":
            return False, None, "非 manual 任务"
        if detect_rubric_format(raw.get("rubric")) != "tree":
            return False, None, "非 tree rubric"
        case_dir = self.result_base_dir / model_id / task_name
        try:
            run_dir = resolve_run_dir(case_dir, run_id)
        except (ValueError, FileNotFoundError):
            return False, None, f"run {run_id} 不可解析"
        score_path = run_dir / "score.json"
        if not score_path.is_file():
            return False, None, "score.json 不存在"
        if skip_existing:
            try:
                score = json.loads(score_path.read_text(encoding="utf-8"))
                if isinstance(score, dict) and "agent_review" in score:
                    return False, None, "已有 agent_review（skip_existing）"
            except (OSError, ValueError):
                pass
        if self.agent_manager is not None:
            existing = self.agent_manager.get_task(
                AgentTaskManager.task_key(model_id, task_name, run_id)
            )
            if existing is not None and existing.status == AgentEvalStatus.RUNNING:
                return False, None, "已有运行中评测"
        task = BatchTask(
            task_key=AgentTaskManager.task_key(model_id, task_name, run_id),
            model_id=model_id,
            task_name=task_name,
            run_id=run_id,
            config=raw,
            task_dir=self.tasks_dir / task_name,
            result_dir=run_dir,
        )
        return True, task, ""

    # ------------------------------------------------------------ 启动/取消

    def start_batch(
        self,
        *,
        model_id: str,
        task_names: list[str],
        evaluate_trace: bool = False,
        skip_existing: bool = True,
        auto_adopt: bool = False,
        concurrency: int = DEFAULT_CONCURRENCY,
        run_id: str = "run_1",
    ) -> BatchEvalSession:
        """批量评测：不合资格的任务计入 `skipped`。batch id：
        `batch_{YYYYmmdd_HHMMSS}_{uuid4().hex[:6]}`。
        """
        tasks: list[BatchTask] = []
        skipped = 0
        for task_name in task_names:
            eligible, task, reason = self._check_eligibility(
                model_id, task_name, run_id, skip_existing
            )
            if eligible and task is not None:
                tasks.append(task)
            else:
                skipped += 1
                print(f"[batch] 跳过 {task_name}：{reason}")
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        session = BatchEvalSession(
            batch_id=batch_id,
            tasks=tasks,
            total=len(task_names),
            skipped=skipped,
            started=len(tasks),
            concurrency=max(1, min(concurrency, len(tasks))),
            auto_adopt=auto_adopt,
            evaluate_trace=evaluate_trace,
            run_id=run_id,
            started_at=_now().isoformat(),
        )
        self._sessions[batch_id] = session
        # 调度执行：优先当前运行中的 loop（async 上下文）；否则起一个守护线程 loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            import threading

            loop = asyncio.new_event_loop()
            threading.Thread(target=loop.run_forever, daemon=True).start()
        loop.call_soon_threadsafe(lambda: loop.create_task(self._run_batch(session)))
        return session

    def cancel_batch(self, batch_id: str) -> Optional[BatchEvalSession]:
        """`cancelled=True`，QUEUED 立即置 CANCELLED，RUNNING 自然跑完；
        worker 见 CANCELLED 任务跳过。
        """
        session = self._sessions.get(batch_id)
        if session is None:
            return None
        session.cancelled = True
        for task in session.tasks:
            if task.status == BatchTaskStatus.QUEUED:
                task.status = BatchTaskStatus.CANCELLED
        return session

    # ------------------------------------------------------------ 执行

    async def _run_batch(self, session: BatchEvalSession) -> None:
        queue: asyncio.Queue[BatchTask] = asyncio.Queue()
        for task in session.tasks:
            queue.put_nowait(task)
        worker_count = max(1, min(session.concurrency, len(session.tasks)))
        workers = [
            asyncio.create_task(self._worker(queue, session)) for _ in range(worker_count)
        ]
        await queue.join()
        for worker in workers:
            worker.cancel()
        session.finished_at = _now().isoformat()

    async def _worker(self, queue: asyncio.Queue[BatchTask], session: BatchEvalSession) -> None:
        while True:
            task = await queue.get()
            try:
                if session.cancelled or task.status == BatchTaskStatus.CANCELLED:
                    continue
                await self._run_task_with_retry(task, session)
            finally:
                queue.task_done()

    async def _run_task_with_retry(self, task: BatchTask, session: BatchEvalSession) -> None:
        task.status = BatchTaskStatus.RUNNING
        timeout = self._timeout_seconds()
        scorer = self._scorer_factory()
        config = TaskConfig.model_validate(task.config)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                review: AgentReview = await asyncio.wait_for(
                    scorer.evaluate(config, session.evaluate_trace, task.task_dir, task.result_dir),
                    timeout=timeout,
                )
            except AgentConcurrentError as exc:
                # 重试无意义
                task.status = BatchTaskStatus.FAILED
                task.error = str(exc)
                return
            except asyncio.TimeoutError:
                if attempt >= MAX_ATTEMPTS:
                    task.status = BatchTaskStatus.TIMEOUT
                    task.error = "Evaluation timed out (after retry)"
                    return
                task.retried = True
                continue
            except Exception as exc:  # noqa: BLE001
                if attempt >= MAX_ATTEMPTS:
                    task.status = BatchTaskStatus.FAILED
                    task.error = f"{exc} (after retry)"
                    return
                task.retried = True
                continue
            task.status = BatchTaskStatus.COMPLETED
            task.score = self._compute_score_from_review(review, task.config)
            if session.auto_adopt:
                self._adopt_one(task, review, session.run_id)
            return

    # ------------------------------------------------------------ 采纳

    @staticmethod
    def _compute_score_from_review(review: AgentReview, raw_config: dict) -> float:
        """`round(quality_score, 4)`，**不持久化**（显示百分比用）。"""
        rubric = QueryRubric.model_validate(raw_config.get("rubric"))
        leaf_bools = {
            leaf: (bool(value.get("passed")) if isinstance(value, dict) else bool(value))
            for leaf, value in review.rubric_results.items()
        }
        return round(compute_rubric_score(rubric, leaf_bools)["quality_score"], 4)

    def _adopt_one(self, task: BatchTask, review: AgentReview, run_id: str) -> None:
        """采纳（tree 派生）：compute_rubric_score 权威派生 → save_manual_score；
        含 trace_quality 时一并保存。不采纳时用 `_compute_score_from_review` 显示百分比。
        """
        if self.loader is None:
            return
        rubric = QueryRubric.model_validate(task.config.get("rubric"))
        leaf_bools = {
            leaf: (bool(value.get("passed")) if isinstance(value, dict) else bool(value))
            for leaf, value in review.rubric_results.items()
        }
        derived = compute_rubric_score(rubric, leaf_bools)
        comment = "\n".join(
            f"[{leaf}] {'✓' if (value.get('passed') if isinstance(value, dict) else value) else '✗'} "
            f"{(value.get('reasoning') if isinstance(value, dict) else '') or ''}"
            for leaf, value in review.rubric_results.items()
        )
        self.loader.save_manual_score(
            model_id=task.model_id,
            task_name=task.task_name,
            run_id=run_id,
            score=round(derived["quality_score"], 4),
            rubric_results=leaf_bools,
            completion=derived["completion"],
            quality_score=derived["quality_score"],
            completion_rate=derived["completion_rate"],
            complete_flag=derived["complete_flag"],
            comment=comment,
            scored_by="agent",
            adopted_agent_timestamp=review.timestamp,
        )
        if review.trace_quality is not None:
            self.loader.save_trace_quality(task.model_id, task.task_name, run_id, review.trace_quality)
