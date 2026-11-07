"""Agent 评测数据模型：AgentReview / AgentEvalTask / AgentEvalStatus。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AgentEvalStatus(str, Enum):
    PENDING = "pending"  # 定义但实际不进入（start_eval 直接建 RUNNING 任务）
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class AgentReview:
    """Agent 评测结果。`to_dict()` 恒写 rubric_format/confidence/timestamp/needs_human_review，
    其余非 None 才写；`from_dict()` 带默认值兼容旧数据。
    """

    rubric_format: str = "tree"
    rubric_results: dict[str, dict[str, Any]] = field(default_factory=dict)  # leaf → {passed, reasoning}
    confidence: float = 0.0
    trace_quality: Optional[dict[str, Any]] = None  # {dimensions: {...}}
    time_analysis: Optional[str] = None
    info_fidelity_analysis: Optional[str] = None
    needs_human_review: bool = False
    review_notes: Optional[str] = None
    timestamp: str = ""

    def to_dict(self) -> dict:
        data: dict[str, Any] = {
            "rubric_format": self.rubric_format,
            "rubric_results": self.rubric_results,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "needs_human_review": self.needs_human_review,
        }
        if self.trace_quality is not None:
            data["trace_quality"] = self.trace_quality
        if self.time_analysis is not None:
            data["time_analysis"] = self.time_analysis
        if self.info_fidelity_analysis is not None:
            data["info_fidelity_analysis"] = self.info_fidelity_analysis
        if self.review_notes is not None:
            data["review_notes"] = self.review_notes
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentReview":
        return cls(
            rubric_format=data.get("rubric_format", "tree"),
            rubric_results=data.get("rubric_results") or {},
            confidence=float(data.get("confidence") or 0.0),
            trace_quality=data.get("trace_quality"),
            time_analysis=data.get("time_analysis"),
            info_fidelity_analysis=data.get("info_fidelity_analysis"),
            needs_human_review=bool(data.get("needs_human_review", False)),
            review_notes=data.get("review_notes"),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class AgentEvalTask:
    """单任务评测状态（key 含 run_id，防止跨 run 冲突）。"""

    task_key: str
    model_id: str
    task_name: str
    run_id: str
    status: AgentEvalStatus = AgentEvalStatus.RUNNING
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "task_key": self.task_key,
            "status": self.status.value,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "run_id": self.run_id,
        }
