"""双格式检测测试（src/rubric/compat.py）。"""

from src.rubric.compat import detect_rubric_format, detect_score_format

TREE = {
    "completion_rubric": [{"id": "a", "type": "leaf", "name": "A"}],
    "quality_rubric": [{"weight": 1.0, "node": {"id": "q", "type": "leaf", "name": "Q"}}],
}
FLAT = [{"completion_rubric": "做A", "quality_rubric": {"1.0": "好"}}]


def test_detect_rubric_format_tree_by_completion():
    assert detect_rubric_format(TREE) == "tree"


def test_detect_rubric_format_tree_by_quality_node():
    rubric = {"quality_rubric": [{"weight": 1.0, "node": {"id": "q", "type": "leaf"}}]}
    assert detect_rubric_format(rubric) == "tree"


def test_detect_rubric_format_explicit_hint():
    assert detect_rubric_format({"rubric_format": "tree", "completion_rubric": []}) == "tree"
    assert detect_rubric_format({"rubric_format": "flat"}) == "flat"


def test_detect_rubric_format_flat_default():
    assert detect_rubric_format(FLAT) == "flat"
    assert detect_rubric_format(None) == "flat"
    assert detect_rubric_format({}) == "flat"
    assert detect_rubric_format("whatever") == "flat"


def test_detect_score_format():
    assert detect_score_format({"rubric_format": "tree"}) == "tree"
    assert detect_score_format({"rubric_results": {"a": True}}) == "tree"
    assert detect_score_format({"rubric_scores": []}) == "flat"
    assert detect_score_format({"manual_score": 0.5}) == "legacy"
    assert detect_score_format(None) == "legacy"
