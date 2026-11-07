"""优化运行（PROMPT-R）的数据模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .models import new_id, now_iso


class ScoreEntry(BaseModel):
    """一条 rubric 的评分记录：gold 标准分 + 各评分者分数。"""

    rubric_id: str
    gold_score: float
    rater_scores: dict[str, float] = Field(default_factory=dict)


class ScoreSheet(BaseModel):
    """一轮的评分表。"""

    entries: list[ScoreEntry] = Field(default_factory=list)


class RoundMetrics(BaseModel):
    """一轮的一致性指标。"""

    pearson_r: float | None = None
    spearman_rho: float | None = None
    qwk: float | None = None
    composite: float | None = None
    per_query_deviation: dict[str, float] = Field(default_factory=dict)  # rubric_id -> 评分者均值 - gold
    n_entries: int = 0
    error: str | None = None
    computed_at: str = Field(default_factory=now_iso)


class FailureFinding(BaseModel):
    """RIFT 单条失败模式诊断。"""

    pattern: str
    node_name: str = ""
    category: str = "quality"
    evidence: str = ""
    severity: str = "medium"
    suggestion: str = ""


class RoundDiagnosis(BaseModel):
    """一轮的诊断结果。"""

    findings: list[FailureFinding] = Field(default_factory=list)
    aggregated: str = ""
    errors: list[dict] = Field(default_factory=list)


class RoundQualityReview(BaseModel):
    """一轮批量 rubric 的人工质量初筛（整批一次判断）。

    decision: "approved"（尚可，进入评分流程）/ "rejected"（不行，跳过评分直接诊断）。
    单条覆盖式记录（可改判窗口内反复提交即覆盖，updated_at 刷新、created_at 保留首判时间）。
    """

    decision: str
    comment: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class OptimizationSuggestion(BaseModel):
    """聚合诊断产出的优化建议。"""

    id: str = Field(default_factory=lambda: new_id("suggestion"))
    module: str  # role/structure/principles/examples/constraints/capabilities/output
    problem: str = ""
    suggestion: str = ""
    status: str = "pending"  # pending / accepted / rejected
    accepted: bool = False


class RoundResult(BaseModel):
    """一个优化轮次。"""

    round_number: int
    prompt_version: str
    status: str = "generating"  # generating/generated/rejected/scored/metrics/analyzed/refined/generate_error
    generation_task_id: str | None = None
    score_sheet: ScoreSheet = Field(default_factory=ScoreSheet)
    metrics: RoundMetrics | None = None
    quality_review: RoundQualityReview | None = None
    diagnosis: RoundDiagnosis | None = None
    suggestions: list[OptimizationSuggestion] = Field(default_factory=list)
    refined_prompt_version: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class StoppingCheck(BaseModel):
    """中止判断结果。"""

    should_stop: bool
    reason: str = ""
    metrics: RoundMetrics | None = None
    thresholds: dict = Field(default_factory=dict)


class OptimizationRun(BaseModel):
    """一次 PROMPT-R 优化运行。"""

    run_id: str = Field(default_factory=lambda: new_id("run"))
    name: str = ""
    query_ids: list[str] = Field(default_factory=list)
    rater_ids: list[str] = Field(default_factory=list)  # 参与打分的评分者（含 gold）
    current_prompt_version: str = ""
    status: str = "running"  # running / converged / stopped 等
    rounds: list[RoundResult] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
