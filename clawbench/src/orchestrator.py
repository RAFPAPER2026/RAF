"""任务编排与并行执行（ThreadPoolExecutor）。"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from src.i18n import current_language
from src.logging_setup import LOG_FILE_NAME, setup_logging
from src.models import TaskConfig
from src.runner import TaskRunner
from src.runs import discover_runs, list_model_runs, resolve_run_dir, write_result_json

logger = logging.getLogger(__name__)


def _pascal(segment: str) -> str:
    """tasks 目录末段 → PascalCase（tasks → Tasks）。"""
    return "".join(part.capitalize() for part in segment.replace("-", "_").split("_"))


def build_result_dir_name(
    tasks_dir: str | Path,
    model_name: str | None = None,
    timestamp: str | None = None,
    uuid8: str | None = None,
) -> str:
    """`{tasks 目录末段 PascalCase}_{model_name}_{timestamp}_{uuid8}`，
    未指定 `--model-name` 时省略中段。
    """
    segment = Path(tasks_dir).name
    language = current_language()
    timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    uuid8 = uuid8 or uuid.uuid4().hex[:8]
    parts = [_pascal(segment)]
    if language == "en":
        parts[0] += "EN"
    if model_name:
        parts.append(model_name)
    parts += [timestamp, uuid8]
    return "_".join(parts)


class Orchestrator:
    """任务编排：load 任务 → 每任务每 run 提交线程池 → 逐个完成重建 result.json。"""

    def __init__(
        self,
        tasks_dir: str | Path,
        result_base_dir: str | Path = "results",
        workers: int = 4,
        runs: int = 1,
        model_name: str | None = None,
        retries: int = 0,
        gateway_timeout: int = 1800,
    ):
        self.tasks_dir = Path(tasks_dir)
        self.result_base_dir = Path(result_base_dir)
        self.workers = workers
        self.runs = runs
        self.model_name = model_name
        self.retries = retries
        self.gateway_timeout = gateway_timeout

    def load_tasks(self) -> list[tuple[str, TaskConfig, Path]]:
        """tasks_dir 下每个含 config.json 的子目录为一个任务。"""
        if not self.tasks_dir.is_dir():
            raise FileNotFoundError(f"tasks 目录不存在：{self.tasks_dir}")
        tasks: list[tuple[str, TaskConfig, Path]] = []
        for child in sorted(self.tasks_dir.iterdir()):
            if child.is_dir() and TaskConfig.config_path(child).is_file():
                try:
                    config = TaskConfig.load(child)
                except (OSError, ValueError, TypeError) as exc:
                    logger.warning("任务配置加载失败 %s：%s", child.name, exc)
                    continue
                tasks.append((child.name, config, child))
        return tasks

    def run(self, result_dir_name: str | None = None) -> Path:
        setup_logging()  # 控制台先行，结果目录确定后再落盘
        tasks = self.load_tasks()
        if not tasks:
            raise ValueError(f"tasks 目录无任务：{self.tasks_dir}")
        result_dir = self.result_base_dir / (
            result_dir_name or build_result_dir_name(self.tasks_dir.name, self.model_name)
        )
        result_dir.mkdir(parents=True, exist_ok=True)
        setup_logging(result_dir)  # 日志文件直接落在结果目录：{result_dir}/eval.log
        logger.info("评测结果目录：%s", result_dir)

        jobs = [
            (task_name, config, task_dir, f"run_{i}")
            for task_name, config, task_dir in tasks
            for i in range(1, self.runs + 1)
        ]
        logger.info(
            "评测开始：%d 个任务 × %d 轮 = %d 个 job，workers=%d",
            len(tasks), self.runs, len(jobs), self.workers,
        )
        runner = TaskRunner(gateway_timeout=self.gateway_timeout, tasks_dir=self.tasks_dir)
        lock = threading.Lock()
        total = len(jobs)
        done = 0
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {
                pool.submit(self._run_job, runner, result_dir, job): job for job in jobs
            }
            for future in as_completed(futures):
                task_name, _, _, run_id = futures[future]
                try:
                    score_data = future.result()
                except Exception as exc:  # noqa: BLE001 - 失败任务不阻断其余任务
                    logger.error("%s/%s 执行异常：%s", task_name, run_id, exc)
                    score_data = None
                done += 1
                status = (score_data or {}).get("status", "unknown")
                score = (score_data or {}).get("score")
                duration = (score_data or {}).get("duration")
                logger.info(
                    "进度 %d/%d：%s/%s 完成 status=%s score=%s 耗时=%ss",
                    done, total, task_name, run_id, status, score, duration,
                )
                with lock:
                    # 每完成一个任务即重建 result.json（损坏的 result.json 整体重建）
                    write_result_json(result_dir)
        logger.info("评测结束：%d/%d 个 job 完成，结果目录 %s", done, total, result_dir)
        write_result_json(result_dir)
        return result_dir

    def _run_job(
        self, runner: TaskRunner, result_dir: Path, job: tuple[str, TaskConfig, Path, str]
    ) -> dict:
        task_name, config, task_dir, run_id = job
        run_dir = result_dir / task_name / run_id
        for attempt in range(self.retries + 1):
            logger.info("提交 %s/%s（第 %d 次尝试）", task_name, run_id, attempt + 1)
            try:
                score_data = runner.run_task(config, task_dir, run_dir, run_id, attempt)
            except Exception as exc:  # noqa: BLE001
                if attempt >= self.retries:
                    raise
                logger.warning("%s/%s 第 %d 次失败：%s，重试", task_name, run_id, attempt + 1, exc)
                continue
            if score_data.get("status") == "completed" or attempt >= self.retries:
                return score_data
            logger.warning(
                "%s/%s 状态 %s，重试", task_name, run_id, score_data.get("status")
            )
        return {}


def rerun_failed(
    result_dir: str | Path,
    tasks_dir: str | Path,
    workers: int = 4,
    retries: int = 0,
    gateway_timeout: int = 1800,
) -> Path:
    """重跑既有结果目录中的失败任务，写入新 run（`run_{max_run+1}`）。"""
    result_dir = Path(result_dir)
    tasks_dir = Path(tasks_dir)
    if not result_dir.is_dir():
        raise FileNotFoundError(f"结果目录不存在：{result_dir}")
    setup_logging(result_dir)  # 复用结果目录既有的 {result_dir}/eval.log
    orchestrator = Orchestrator(tasks_dir, result_dir.parent, workers=workers)
    tasks = orchestrator.load_tasks()
    new_run = f"run_{list_model_runs(result_dir)['max_run'] + 1}"
    jobs: list[tuple[str, TaskConfig, Path]] = []
    for task_name, config, task_dir in tasks:
        case_dir = result_dir / task_name
        runs = discover_runs(case_dir)
        failed = True
        if runs:
            try:
                last_dir = resolve_run_dir(case_dir, runs[-1])
                data = json.loads((last_dir / "score.json").read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("status") == "completed" and not data.get("error"):
                    failed = False
            except (OSError, ValueError):
                failed = True
        if failed:
            jobs.append((task_name, config, task_dir))
    if not jobs:
        logger.info("没有失败任务，无需重跑")
        return result_dir
    logger.info("重跑 %d 个失败任务 → %s（日志：%s）", len(jobs), new_run, result_dir / LOG_FILE_NAME)
    runner = TaskRunner(gateway_timeout=gateway_timeout, tasks_dir=tasks_dir)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(runner.run_task, config, task_dir, result_dir / task_name / new_run, new_run, 0): task_name
            for task_name, config, task_dir in jobs
        }
        for future in as_completed(futures):
            task_name = futures[future]
            try:
                score_data = future.result()
                logger.info(
                    "重跑完成 %s/%s status=%s score=%s", task_name, new_run,
                    (score_data or {}).get("status"), (score_data or {}).get("score"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("%s 重跑异常：%s", task_name, exc)
    write_result_json(result_dir)
    return result_dir
