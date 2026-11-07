"""flat→tree 迁移测试（src/rubric/migrate.py）。"""

from src.rubric.compat import detect_rubric_format
from src.rubric.migrate import FLAT_QUALITY_WEIGHT, flat_rubric_to_tree
from src.rubric.scoring import collect_leaf_ids


def test_flat_rubric_to_tree_structure():
    flat = [
        {"completion_rubric": "完成A", "quality_rubric": {"1.0": "好"}, "tags": ["t1"]},
        {"completion_rubric": "完成B", "quality_rubric": {"1.0": "好"}},
    ]
    tree = flat_rubric_to_tree(flat, rubric_id="r1", query="q1")
    assert detect_rubric_format(tree.model_dump()) == "tree"
    assert tree.id == "r1"
    assert tree.query == "q1"
    # 完成树：顶层 AND 组 node-flat-root「完成项」，镜像「全部项须通过」
    assert len(tree.completion_rubric) == 1
    root = tree.completion_rubric[0]
    assert root.id == "node-flat-root"
    assert root.combinator == "and"
    assert root.name == "完成项"
    assert [leaf.id for leaf in root.children] == ["node-flat-0000", "node-flat-0001"]
    # 质量树：每项一个质量叶子，weight 3.0
    assert [item.node.id for item in tree.quality_rubric] == ["node-flat-q-0000", "node-flat-q-0001"]
    assert all(item.weight == FLAT_QUALITY_WEIGHT for item in tree.quality_rubric)
    # 叶子收集（完成 + 质量）
    leaves = collect_leaf_ids(tree)
    assert "node-flat-0000" in leaves and "node-flat-q-0001" in leaves
    # 标签透传
    assert "t1" in root.children[0].tags
    assert "t1" in tree.quality_rubric[0].node.tags


def test_flat_rubric_to_tree_empty():
    tree = flat_rubric_to_tree([])
    assert tree.completion_rubric == []
    assert tree.quality_rubric == []
