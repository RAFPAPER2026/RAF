"""RAF 评分算法测试（rubric/scoring.py）。"""

from __future__ import annotations

import pytest

from rubric.models import RubricNode, WeightedItem
from rubric.scoring import (
    collect_all_leaf_ids,
    evaluate_completion,
    evaluate_node_score,
    score_quality,
)


def _rubric_nodes():
    return [
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
    ]


def test_completion_is_all_pass():
    assert evaluate_completion(_rubric_nodes(), {"a": True, "b": False, "c": True})["completed"] is True
    assert evaluate_completion(_rubric_nodes(), {"a": True, "b": False, "c": False})["completed"] is False


def test_quality_and_group_paper_vs_legacy():
    group = RubricNode(
        id="g",
        type="group",
        name="G",
        combinator="and",
        children=[RubricNode(id="x", type="leaf", name="X"), RubricNode(id="y", type="leaf", name="Y")],
    )
    assert evaluate_node_score(group, {"x": True, "y": True}, "paper") == 1.0
    assert evaluate_node_score(group, {"x": True, "y": False}, "paper") == 0.0
    assert evaluate_node_score(group, {"x": True, "y": False}, "legacy_mean") == 0.5


def test_quality_or_group_takes_max():
    group = RubricNode(
        id="g",
        type="group",
        name="G",
        combinator="or",
        children=[RubricNode(id="x", type="leaf", name="X"), RubricNode(id="y", type="leaf", name="Y")],
    )
    assert evaluate_node_score(group, {"x": True, "y": False}, "paper") == 1.0


def test_quality_weighted_average():
    items = [
        WeightedItem(weight=2.0, node=RubricNode(id="q1", type="leaf", name="Q1")),
        WeightedItem(weight=1.0, node=RubricNode(id="q2", type="leaf", name="Q2")),
    ]
    result = score_quality(items, {"q1": True, "q2": False}, "paper")
    assert result["score"] == pytest.approx(2 / 3)
    assert result["scoringMode"] == "paper"


def test_invalid_mode_rejected():
    node = RubricNode(id="q", type="leaf", name="Q")
    with pytest.raises(ValueError):
        evaluate_node_score(node, {}, "unknown")


def test_collect_leaf_ids():
    nodes = _rubric_nodes() + [
        WeightedItem(weight=1.0, node=RubricNode(id="q", type="leaf", name="Q")).node
    ]
    assert collect_all_leaf_ids(nodes) == ["a", "b", "c", "q"]
