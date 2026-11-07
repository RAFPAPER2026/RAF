"""评分框架（单一事实来源，纯逻辑，无 IO）。

被 manual_scorer、src/analyzer、src/visualizer、src/agent_scorer 共同引用。
前端 web/src/rubric/scoring.ts 是 Python 评分逻辑的手工同步镜像。
"""

from src.rubric.compat import detect_rubric_format, detect_score_format
from src.rubric.migrate import flat_rubric_to_tree
from src.rubric.models import QueryRubric, RubricNode, RubricResults, WeightedItem
from src.rubric.scoring import (
    collect_leaf_ids,
    compute_rubric_score,
    evaluate_completion,
    score_quality,
)

__all__ = [
    "RubricNode",
    "WeightedItem",
    "QueryRubric",
    "RubricResults",
    "evaluate_completion",
    "score_quality",
    "compute_rubric_score",
    "collect_leaf_ids",
    "detect_rubric_format",
    "detect_score_format",
    "flat_rubric_to_tree",
]
