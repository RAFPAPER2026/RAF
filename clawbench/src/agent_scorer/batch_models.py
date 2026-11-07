"""BatchEvalSession / BatchTaskStatus（批量评测会话模型）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class BatchTaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class BatchTask:
    task_key: str
    model_id: str
    task_name: str
    run_id: str
    config: dict
    task_dir: Path
    result_dir: Path  # 具体 run 的结果目录（score.json 所在目录）
    status: BatchTaskStatus = BatchTaskStatus.QUEUED
    score: Optional[float] = None
    error: Optional[str] = None
    retried: bool = False

    def to_dict(self) -> dict:
        return {
            "task_key": self.task_key,
            "task_name": self.task_name,
            "run_id": self.run_id,
            "status": self.status.value,
            "score": self.score,
            "error": self.error,
            "retried": self.retried,
        }


@dataclass
class BatchEvalSession:
    batch_id: str
    tasks: list[BatchTask] = field(default_factory=list)
    total: int = 0
    skipped: int = 0
    started: int = 0
    concurrency: int = 1
    auto_adopt: bool = False
    evaluate_trace: bool = False
    run_id: str = "run_1"
    cancelled: bool = False
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def summary(self) -> dict:
        """计数各状态。"""
        counts = {status.value: 0 for status in BatchTaskStatus}
        for task in self.tasks:
            counts[task.status.value] += 1
        return counts

    # 会话级聚合视图（由 tasks 派生）
    @property
    def results(self) -> dict[str, str]:
        """`{task_key: status}`。"""
        return {t.task_key: t.status.value for t in self.tasks}

    @property
    def errors(self) -> dict[str, Optional[str]]:
        """`{task_key: error}`。"""
        return {t.task_key: t.error for t in self.tasks}

    @property
    def scores(self) -> dict[str, Optional[float]]:
        """`{task_key: score}`。"""
        return {t.task_key: t.score for t in self.tasks}

    @property
    def retried(self) -> dict[str, bool]:
        """`{task_key: retried}`。"""
        return {t.task_key: t.retried for t in self.tasks}

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "status": self._status_label(),
            "tasks": [task.to_dict() for task in self.tasks],
            "total": self.total,
            "skipped": self.skipped,
            "started": self.started,
            "concurrency": self.concurrency,
            "auto_adopt": self.auto_adopt,
            "evaluate_trace": self.evaluate_trace,
            "run_id": self.run_id,
            "cancelled": self.cancelled,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary(),
        }

    def _status_label(self) -> str:
        if self.finished_at is None:
            return "running"
        return "cancelled" if self.cancelled else "finished"
