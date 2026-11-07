"""评分公式测试（src/rubric/scoring.py）。"""

from src.rubric.models import QueryRubric, RubricNode, WeightedItem
from src.rubric.scoring import (
    collect_leaf_ids,
    compute_rubric_score,
    evaluate_completion,
    score_quality,
)


def _rubric() -> QueryRubric:
    return QueryRubric(
        completion_rubric=[
            RubricNode(id="a", type="leaf", name="A"),
            RubricNode(
                id="bc",
                type="group",
                combinator="or",
                name="BC",
                children=[
                    RubricNode(id="b", type="leaf", name="B"),
                    RubricNode(id="c", type="leaf", name="C"),
                ],
            ),
        ],
        quality_rubric=[
            WeightedItem(weight=2.0, node=RubricNode(id="q1", type="leaf", name="Q1")),
            WeightedItem(weight=1.0, node=RubricNode(id="q2", type="leaf", name="Q2")),
        ],
    )


def test_completion_all_pass():
    r = evaluate_completion(_rubric().completion_rubric, {"a": True, "b": False, "c": True})
    assert r["completed"] is True  # a ✓；or 组（b ✗, c ✓）→ any → ✓
    assert r["total"] == 3
    assert r["passed"] == 2


def test_completion_missing_leaf_is_fail():
    """缺失叶子视为失败：or 组 b/c 都缺失 → 组失败 → completed False。"""
    r = evaluate_completion(_rubric().completion_rubric, {"a": True})
    assert r["completed"] is False  # or(b 缺失✗, c 缺失✗) → False


def test_empty_group_vacuous_completion_but_zero_quality():
    node = RubricNode(id="g", type="group", combinator="and", name="空组")
    assert evaluate_completion([node], {})["completed"] is True  # all([]) == True
    assert score_quality([WeightedItem(weight=1.0, node=node)], {})["score"] == 0.0  # 显式 0.0


def test_empty_trees():
    assert evaluate_completion([], {})["completed"] is True  # 无项时 completed=True
    assert score_quality([], {})["score"] == 0.0  # quality_rubric 为空 → 0.0


def test_quality_weighted_average():
    q = score_quality(_rubric().quality_rubric, {"q1": True, "q2": False})
    assert q["score"] == 2.0 / 3.0  # (2*1 + 1*0) / 3
    assert q["total_weight"] == 3.0
    assert q["weighted_completed"] == 2.0


def test_quality_or_max():
    group = RubricNode(
        id="g",
        type="group",
        combinator="or",
        children=[RubricNode(id="x", type="leaf"), RubricNode(id="y", type="leaf")],
    )
    q = score_quality([WeightedItem(weight=1.0, node=group)], {"x": True, "y": False})
    assert q["score"] == 1.0  # or=max


def test_compute_rubric_score_fields():
    result = compute_rubric_score(
        _rubric(), {"a": True, "b": True, "c": False, "q1": True, "q2": True}
    )
    assert set(result) >= {
        "completion", "quality", "quality_score", "score", "completion_rate", "complete_flag",
    }
    assert result["score"] == result["quality_score"] == 1.0
    assert result["complete_flag"] == 1
    assert abs(result["completion_rate"] - 2 / 3) < 1e-9
    result2 = compute_rubric_score(
        _rubric(), {"a": False, "b": False, "c": False, "q1": False, "q2": False}
    )
    assert result2["complete_flag"] == 0


def test_collect_leaf_ids_dfs_order():
    assert collect_leaf_ids(_rubric()) == ["a", "b", "c", "q1", "q2"]


def _and_group_item():
    group = RubricNode(
        id="g",
        type="group",
        combinator="and",
        children=[RubricNode(id="x", type="leaf"), RubricNode(id="y", type="leaf")],
    )
    return [WeightedItem(weight=1.0, node=group)]


def test_and_group_paper_mode_is_binary():
    """论文口径：AND 组全过才得 1，否则 0。"""
    assert score_quality(_and_group_item(), {"x": True, "y": True}, "paper")["score"] == 1.0
    assert score_quality(_and_group_item(), {"x": True, "y": False}, "paper")["score"] == 0.0


def test_and_group_legacy_mode_is_mean():
    """兼容口径：AND 组取子节点均值。"""
    assert score_quality(_and_group_item(), {"x": True, "y": False}, "legacy_mean")["score"] == 0.5


def test_scoring_mode_is_reported_and_env_configurable(monkeypatch):
    result = compute_rubric_score(_rubric(), {"a": True, "b": True, "c": True, "q1": True, "q2": True})
    assert result["scoring_mode"] == "paper"
    monkeypatch.setenv("CLAWBENCH_SCORING_MODE", "legacy_mean")
    result2 = compute_rubric_score(
        _rubric(), {"a": True, "b": True, "c": True, "q1": True, "q2": True}
    )
    assert result2["scoring_mode"] == "legacy_mean"


def test_invalid_scoring_mode_rejected():
    import pytest

    with pytest.raises(ValueError):
        score_quality(_and_group_item(), {"x": True, "y": True}, "unknown")

