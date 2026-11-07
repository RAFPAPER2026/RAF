"""采纳测试：to_dict/from_dict roundtrip、采纳派生。"""

from src.agent_scorer.models import AgentReview
from src.rubric.models import QueryRubric, RubricNode, WeightedItem
from src.rubric.scoring import compute_rubric_score


def test_agent_review_roundtrip():
    review = AgentReview(
        rubric_format="tree",
        rubric_results={"leaf-a": {"passed": True, "reasoning": "证据"}},
        confidence=0.9,
        trace_quality={"dimensions": {"task_understanding": 1.0}},
        time_analysis="无时间窗口要求",
        info_fidelity_analysis="无搜索信息忠实性要求",
        needs_human_review=False,
        review_notes="无需人工复核",
        timestamp="2026-08-21T00:00:00+00:00",
    )
    assert AgentReview.from_dict(review.to_dict()) == review


def test_agent_review_to_dict_omits_none_fields():
    review = AgentReview(needs_human_review=False, timestamp="t")
    data = review.to_dict()
    for field in ("rubric_format", "confidence", "timestamp", "needs_human_review"):
        assert field in data
    assert "trace_quality" not in data
    assert "time_analysis" not in data


def test_agent_review_from_dict_defaults():
    restored = AgentReview.from_dict({})
    assert restored.rubric_format == "tree"
    assert restored.confidence == 0.0
    assert restored.needs_human_review is False
    assert restored.rubric_results == {}


def test_adopt_derived_score():
    """采纳派生：{leaf: {passed, reasoning}} → {leaf: bool} → compute_rubric_score →
    round(quality_score, 4)。
    """
    rubric = QueryRubric(
        completion_rubric=[RubricNode(id="a", type="leaf", name="A")],
        quality_rubric=[
            WeightedItem(weight=2.0, node=RubricNode(id="q", type="leaf", name="Q"))
        ],
    )
    review_results = {
        "a": {"passed": True, "reasoning": "证据"},
        "q": {"passed": True, "reasoning": "证据"},
    }
    leaf_bools = {leaf: bool(v["passed"]) for leaf, v in review_results.items()}
    derived = compute_rubric_score(rubric, leaf_bools)
    assert round(derived["quality_score"], 4) == 1.0
    assert derived["complete_flag"] == 1

    review_results["q"]["passed"] = False
    leaf_bools = {leaf: bool(v["passed"]) for leaf, v in review_results.items()}
    derived = compute_rubric_score(rubric, leaf_bools)
    assert round(derived["quality_score"], 4) == 0.0
    assert derived["complete_flag"] == 1  # 完成树 a ✓（q 是质量叶）


def test_adopt_non_dict_defensive_bool():
    """非 dict 用 bool(v) 防御。"""
    leaf_bools = {leaf: bool(v) for leaf, v in {"a": True, "q": 1}.items()}
    assert leaf_bools == {"a": True, "q": True}
