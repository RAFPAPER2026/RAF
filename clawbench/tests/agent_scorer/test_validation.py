"""校验测试：覆盖全部叶子、多余 key 丢弃回归、confidence 范围、四个必填字段、
trace_quality 归一化。
"""

import pytest

from src.agent_scorer.exceptions import AgentValidationError
from src.agent_scorer.scorer import AgentScorer
from src.rubric.models import QueryRubric, RubricNode, WeightedItem


def _rubric() -> QueryRubric:
    return QueryRubric(
        completion_rubric=[
            RubricNode(id="leaf-a", type="leaf", name="A"),
            RubricNode(
                id="group-b",
                type="group",
                combinator="or",
                name="B",
                children=[
                    RubricNode(id="leaf-b1", type="leaf", name="B1"),
                    RubricNode(id="leaf-b2", type="leaf", name="B2"),
                ],
            ),
        ],
        quality_rubric=[
            WeightedItem(weight=1.0, node=RubricNode(id="leaf-q", type="leaf", name="Q")),
        ],
    )


def _base_output() -> dict:
    leaves = ("leaf-a", "leaf-b1", "leaf-b2", "leaf-q")
    return {
        "rubric_results": {leaf: {"passed": True, "reasoning": "具体理由"} for leaf in leaves},
        "confidence": 0.8,
        "time_analysis": "无时间窗口要求",
        "info_fidelity_analysis": "无搜索信息忠实性要求",
        "needs_human_review": False,
        "review_notes": "无需人工复核",
    }


def test_accepts_complete_output():
    review = AgentScorer._validate_output(_base_output(), _rubric(), False)
    assert review.rubric_results["leaf-a"]["passed"] is True
    assert review.confidence == 0.8


def test_missing_leaf_rejected():
    out = _base_output()
    del out["rubric_results"]["leaf-q"]
    with pytest.raises(AgentValidationError, match="missing leaf ids"):
        AgentScorer._validate_output(out, _rubric(), False)


def test_extra_non_leaf_keys_dropped_regression():
    """多余非叶子 key 静默丢弃（含已知 group id）——回归测试。"""
    out = _base_output()
    out["rubric_results"]["group-b"] = {"passed": True, "reasoning": "组结果"}
    review = AgentScorer._validate_output(out, _rubric(), False)
    assert "group-b" not in review.rubric_results


def test_confidence_range():
    for bad in (-0.1, 1.1, "0.5", None, True):
        out = _base_output()
        out["confidence"] = bad
        with pytest.raises(AgentValidationError):
            AgentScorer._validate_output(out, _rubric(), False)
    out = _base_output()
    out["confidence"] = 1  # int 接受并转 float
    review = AgentScorer._validate_output(out, _rubric(), False)
    assert review.confidence == 1.0


def test_required_text_fields():
    for field in ("time_analysis", "info_fidelity_analysis", "review_notes"):
        for bad in ("", "   ", None, 42):
            out = _base_output()
            out[field] = bad
            with pytest.raises(AgentValidationError, match=field):
                AgentScorer._validate_output(out, _rubric(), False)


def test_needs_human_review_required_bool():
    out = _base_output()
    out["needs_human_review"] = "yes"
    with pytest.raises(AgentValidationError):
        AgentScorer._validate_output(out, _rubric(), False)


def test_trace_quality_normalization():
    out = _base_output()
    out["trace_quality"] = {
        "task_understanding": 0.75,
        "task_planning": 0.5,
        "tool_usage": 0.25,
        "reflection_recovery": 0.0,
    }
    review = AgentScorer._validate_output(out, _rubric(), True)
    assert review.trace_quality["dimensions"]["task_understanding"] == 0.75
    assert review.trace_quality["dimensions"]["reflection_recovery"] == 0.0


def test_trace_quality_accepts_bare_and_wrapped():
    dims = {
        "task_understanding": 1.0,
        "task_planning": 1.0,
        "tool_usage": 1.0,
        "reflection_recovery": 1.0,
    }
    for value in (dims, {"dimensions": dims}):
        out = _base_output()
        out["trace_quality"] = value
        review = AgentScorer._validate_output(out, _rubric(), True)
        assert review.trace_quality["dimensions"]["task_understanding"] == 1.0


def test_trace_quality_off_enum_rejected():
    out = _base_output()
    out["trace_quality"] = {
        "task_understanding": 0.6,  # 容差 1e-3 内不在枚举值
        "task_planning": 0.5,
        "tool_usage": 0.25,
        "reflection_recovery": 0.0,
    }
    with pytest.raises(AgentValidationError):
        AgentScorer._validate_output(out, _rubric(), True)


def test_trace_quality_missing_when_required():
    with pytest.raises(AgentValidationError):
        AgentScorer._validate_output(_base_output(), _rubric(), True)
