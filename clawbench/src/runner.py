"""单任务生命周期（容器→初始化→请求→收集→清理）。

- 起容器（worker 目录挂载 /root/Desktop）→ 环境初始化（init_env 拷贝 + .scripts 宿主机执行 +
  .skills/.preset 挂载）→ 向 gateway 下发任务 → 收集会话与工作区 → 清理容器
- 任务评分统一走人工打分或裁判 agent（`agent_scorer`），runner 不写 `score`/`complete_flag`
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

from src.container_client import ContainerManagerClient, OpenclawGatewayClient
from src.metrics import calculate_metrics
from src.models import STATUS_COMPLETED, STATUS_FAILED, TaskConfig
from src.openclaw_events import read_openclaw_session_file
from src.runs import write_json_atomic

logger = logging.getLogger(__name__)

SKILLS_DIR = ".skills"
SCRIPTS_DIR = ".scripts"
PRESET_DIR = ".preset"
# init_env 拷贝时排除的目录（skills/presets 走挂载，scripts 在宿主机执行）
_EXCLUDED_INIT_DIRS = {SCRIPTS_DIR, SKILLS_DIR, PRESET_DIR}


class TaskRunner:
    """单个任务单轮执行器。"""

    def __init__(
        self,
        container_client: Optional[ContainerManagerClient] = None,
        gateway_timeout: int = 1800,
        manager_url: Optional[str] = None,
        tasks_dir: Optional[str | Path] = None,
    ):
        if container_client is None:
            if manager_url:
                container_client = ContainerManagerClient(base_url=manager_url)
            else:
                container_client = ContainerManagerClient()
        self.container_client = container_client
        self.gateway_timeout = gateway_timeout
        self.tasks_dir = Path(tasks_dir) if tasks_dir else None

    # ------------------------------------------------------------ 主流程

    def run_task(
        self,
        config: TaskConfig,
        task_dir: Path,
        run_dir: Path,
        run_id: str,
        retry_count: int = 0,
    ) -> dict:
        """执行单个任务（一次 run），写入 `run_dir/{score.json, sessions.json,
        workspace/, verifier/}`，返回 score 数据。
        """
        task_name = task_dir.name
        started = time.monotonic()
        score_data: dict[str, Any] = {
            "task_name": task_name,
            "status": STATUS_FAILED,
            "error": None,
            "start_time": datetime.now().isoformat(),
            "retry_count": retry_count,
        }
        container_info: Optional[dict] = None
        worker_path: Optional[Path] = None
        tag = f"[{task_name}/{run_id}]"
        logger.info("%s 开始执行任务：lang=%s，retry=%s", tag, config.language, retry_count)
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            # 1. 起容器（init_env 的 .skills/.preset 一并挂载）
            logger.info("%s 步骤 1/5：创建评测容器…", tag)
            container_info = self._create_container(config, task_dir)
            worker_path = Path(container_info["worker_path"])
            logger.info(
                "%s 容器已创建：name=%s port=%s worker=%s", tag,
                container_info["container_name"], container_info["port"], worker_path,
            )
            # 2. 环境初始化：init_env 拷贝（除 .scripts/.skills/.preset/）+ .scripts 宿主机执行
            logger.info("%s 步骤 2/5：环境初始化（init_env）…", tag)
            self._init_env(task_dir, worker_path)
            logger.info("%s 环境初始化完成", tag)
            # 3. 向 gateway 下发任务（先等 gateway 就绪：容器端口映射先于
            #    gateway 启动完成，过早请求会被对端 RST）
            logger.info("%s 步骤 3/5：等待容器内 gateway 就绪（port=%s）…", tag, container_info["port"])
            self._wait_gateway_ready(container_info["port"])
            logger.info("%s gateway 就绪，下发任务（prompt %d 字符）…", tag, len(config.prompt))
            gateway = OpenclawGatewayClient(
                port=container_info["port"], timeout=self.gateway_timeout
            )
            sent = time.monotonic()
            response = gateway.chat(config.prompt)
            logger.info("%s gateway 响应完成：耗时 %.1fs", tag, time.monotonic() - sent)
            sessions = self._extract_sessions(
                response, container_info["container_name"], worker_path
            )
            session_count = len(sessions.get("sessions") or [])
            write_json_atomic(run_dir / "sessions.json", sessions)
            # 4. 收集工作区（worker 挂载点 → 结果 workspace/）
            logger.info("%s 步骤 4/5：收集会话（%d 条）与工作区…", tag, session_count)
            self._collect_workspace(worker_path, run_dir / "workspace")
            # 5. 指标（token/成本/工具统计）
            score_data.update(
                calculate_metrics(
                    sessions.get("sessions") or [], model_name=self._model_of_response(response)
                )
            )
            logger.info(
                "%s 指标统计：tokens=%s/%s cost=%s 工具=%s 次",
                tag,
                score_data.get("input_tokens"), score_data.get("output_tokens"),
                score_data.get("input_cost"), score_data.get("tool_calls"),
            )
            # 5. 评分不在 runner 中执行：由人工打分页或裁判 agent 写入 score.json /
            #    manual_score / complete_flag。runner 只负责采集轨迹与工作区。
            logger.info("%s 步骤 5/5：采集完成，等待人工或裁判评分", tag)
            score_data["status"] = STATUS_COMPLETED
            score_data["error"] = None
        except Exception as exc:  # noqa: BLE001 - 任务失败统一记录
            score_data["status"] = STATUS_FAILED
            score_data["error"] = str(exc)
            logger.exception("%s 任务失败：%s", tag, exc)
        finally:
            # 7. 清理容器与 worker 目录（工作区已收集，容器产物不留存）
            if container_info is not None:
                try:
                    logger.info("%s 清理容器 %s", tag, container_info["container_name"])
                    self.container_client.delete(container_info["container_name"])
                except Exception as exc:  # noqa: BLE001
                    logger.warning("%s 容器清理失败：%s", tag, exc)
            if worker_path is not None and score_data["status"] == STATUS_COMPLETED:
                shutil.rmtree(worker_path, ignore_errors=True)
            score_data["end_time"] = datetime.now().isoformat()
            score_data["duration"] = round(time.monotonic() - started, 2)
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json_atomic(run_dir / "score.json", score_data)
            if score_data["status"] == STATUS_COMPLETED:
                logger.info(
                    "%s 任务完成：status=%s score=%s 总耗时 %.1fs",
                    tag, score_data["status"], score_data.get("score"), score_data["duration"],
                )
        return score_data

    # ------------------------------------------------------------ 容器与环境

    def _create_container(self, config: TaskConfig, task_dir: Path) -> dict:
        """起容器：worker 目录不显式指定，由容器管理服务按默认目录
        `./workspace/openclaw_workers/{container_name}` 创建并挂载 /root/Desktop；
        init_env 的 .skills/.preset 挂载到 /root/.openclaw/workspace/{skills,presets}；
        openclaw 自定义配置来源：任务 config.json 顶层 `openclaw_config_path` 键优先，
        否则回退到 tasks 目录顶层的共享 `openclaw.json`（整批任务公用一个模型配置）。
        """
        init_env = task_dir / "init_env"
        skills_path = preset_path = None
        if init_env.is_dir():
            if (init_env / SKILLS_DIR).is_dir():
                skills_path = str(init_env / SKILLS_DIR)
            if (init_env / PRESET_DIR).is_dir():
                preset_path = str(init_env / PRESET_DIR)
        extra = config.model_extra or {}
        openclaw_config_path = extra.get("openclaw_config_path")
        if openclaw_config_path is None and self.tasks_dir is not None:
            shared_config = self.tasks_dir / "openclaw.json"
            if shared_config.is_file():
                openclaw_config_path = str(shared_config)
        return self.container_client.start(
            openclaw_config_path=openclaw_config_path,
            skills_path=skills_path,
            preset_path=preset_path,
        )

    @staticmethod
    def _wait_gateway_ready(port: int, timeout: float = 120.0) -> None:
        """轮询容器内 gateway 的 /healthz，直到就绪或超时。"""
        deadline = time.monotonic() + timeout
        last_err: Optional[Exception] = None
        while time.monotonic() < deadline:
            try:
                resp = requests.get(f"http://127.0.0.1:{port}/healthz", timeout=3)
                if resp.status_code == 200:
                    return
            except requests.RequestException as exc:
                last_err = exc
            time.sleep(1)
        raise RuntimeError(f"gateway 未在 {int(timeout)}s 内就绪（最后错误：{last_err}）")

    def _init_env(self, task_dir: Path, worker_path: Path) -> None:
        """`init_env/` 全部拷贝（除 `.scripts/.skills/.preset/`）；
        `.scripts/` 脚本在宿主机执行（.sh→bash、.py→python3）。
        """
        init_env = task_dir / "init_env"
        if not init_env.is_dir():
            return
        worker_path.mkdir(parents=True, exist_ok=True)
        for child in init_env.iterdir():
            if child.name in _EXCLUDED_INIT_DIRS:
                continue
            if child.is_dir():
                shutil.copytree(child, worker_path / child.name, dirs_exist_ok=True)
            else:
                shutil.copy2(child, worker_path / child.name)
        scripts_dir = init_env / SCRIPTS_DIR
        if scripts_dir.is_dir():
            for script in sorted(scripts_dir.iterdir()):
                if script.is_file():
                    self._run_host_script(script, worker_path)

    @staticmethod
    def _run_host_script(script: Path, cwd: Path) -> None:
        name = script.name.lower()
        if name.endswith(".sh"):
            subprocess.run(["bash", str(script)], cwd=str(cwd), check=False, timeout=300)
        elif name.endswith(".py"):
            interpreter = "python3" if shutil.which("python3") else sys.executable
            subprocess.run(
                [interpreter, str(script)], cwd=str(cwd), check=False, timeout=300
            )

    # ------------------------------------------------------------ 结果收集

    @staticmethod
    def _extract_sessions(response: dict, container_name: str, worker_path: Path) -> dict:
        """提取会话事件：优先 gateway 响应中的 session，否则读容器挂载的
        `.openclaw_agents/main/sessions/*.jsonl` 转录（openclaw HTTP API
        响应不带 session，转录经 `{worker_path}/.openclaw_agents` 挂载获取）。
        """
        events = response.get("session") or response.get("sessions") or []
        if isinstance(events, dict):
            events = events.get("sessions") or events.get("entries") or []
        if not isinstance(events, list) or not events:
            events = read_openclaw_session_file(worker_path / ".openclaw_agents")
        return {"container": container_name, "sessions": events}

    @staticmethod
    def _model_of_response(response: dict) -> str:
        model = response.get("model")
        if isinstance(model, str):
            return model
        usage = response.get("usage")
        if isinstance(usage, dict) and isinstance(usage.get("model"), str):
            return usage["model"]
        return ""

    @staticmethod
    def _collect_workspace(worker_path: Path, workspace_dir: Path) -> None:
        """worker 目录（容器 /root/Desktop 挂载点）→ 结果 workspace/。"""
        if not worker_path.is_dir():
            workspace_dir.mkdir(parents=True, exist_ok=True)
            return
        workspace_dir.mkdir(parents=True, exist_ok=True)
        for child in worker_path.iterdir():
            if child.name == ".openclaw_agents":  # 会话转录挂载点，不属工作区产物
                continue
            if child.is_dir():
                shutil.copytree(child, workspace_dir / child.name, dirs_exist_ok=True)
            else:
                shutil.copy2(child, workspace_dir / child.name)
