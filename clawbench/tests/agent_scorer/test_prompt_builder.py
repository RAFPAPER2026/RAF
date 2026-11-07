"""prompt 组装测试：system prompt 无路径/无叶子 id、rubric 树只在 user prompt、
schema 密封、必填字段、flat 抛 ValueError。
"""

import json

import pytest

from src.agent_scorer.prompt_builder import (
    _render_tree,
    build_output_schema,
    build_prompts,
    build_system_prompt,
)
from src.models import TaskConfig
from src.rubric.models import QueryRubric, RubricNode, WeightedItem


def _make_rubric() -> QueryRubric:
    return QueryRubric(
        id="r1",
        query="测试任务",
        completion_rubric=[
            RubricNode(id="leaf-a", type="leaf", name="叶子A"),
            RubricNode(
                id="group-b",
                type="group",
                combinator="or",
                name="或组B",
                children=[
                    RubricNode(id="leaf-b1", type="leaf", name="B1"),
                    RubricNode(id="leaf-b2", type="leaf", name="B2"),
                ],
            ),
        ],
        quality_rubric=[
            WeightedItem(weight=2.0, node=RubricNode(id="leaf-q", type="leaf", name="质量Q")),
        ],
    )


def test_system_prompt_is_case_agnostic():
    """system prompt 无叶子 id、无文件系统路径、无 user prompt 专属小节（测试强制）。"""
    prompt = build_system_prompt(_make_rubric())
    for leaf in ("leaf-a", "leaf-b1", "leaf-b2", "leaf-q"):
        assert leaf not in prompt
    for section in ("## 原始任务提问", "## 任务目录\n\n", "## 结果目录\n\n", "### 完成判定树", "### 质量评分树"):
        assert section not in prompt


def test_system_prompt_trace_quality_section_only_when_enabled():
    assert "过程质量评价" not in build_system_prompt(_make_rubric(), False)
    with_trace = build_system_prompt(_make_rubric(), True)
    assert "过程质量评价" in with_trace
    assert "任务理解 (task_understanding): 0.0/0.25/0.5/0.75/1.0" in with_trace


def test_user_prompt_contains_rubric_tree(tmp_path):
    rubric = _make_rubric()
    config = TaskConfig(id="t1", prompt="帮我做点事", rubric=rubric.model_dump())
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "config.json").write_text(
        json.dumps(config.model_dump(), ensure_ascii=False), encoding="utf-8"
    )
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    system, user, _ = build_prompts(config, False, task_dir, result_dir)
    assert "leaf-a" in user and "叶子A" in user
    assert "OR 组" in user
    assert "完成判定树" in user and "质量评分树" in user
    assert "帮我做点事" in user
    assert "leaf-a" not in system  # rubric 树只在 user prompt


def test_output_schema_sealed():
    rubric = _make_rubric()
    schema = build_output_schema(rubric, False)["schema"]
    rr = schema["properties"]["rubric_results"]
    assert rr["additionalProperties"] is False
    assert set(rr["required"]) == {"leaf-a", "leaf-b1", "leaf-b2", "leaf-q"}
    assert set(rr["properties"]) == {"leaf-a", "leaf-b1", "leaf-b2", "leaf-q"}
    for field in (
        "rubric_results", "confidence", "time_analysis",
        "info_fidelity_analysis", "needs_human_review", "review_notes",
    ):
        assert field in schema["required"]
    assert "trace_quality" not in schema["required"]
    # evaluate_trace：trace_quality 追加在 required 末位
    schema_eval = build_output_schema(rubric, True)["schema"]
    assert schema_eval["required"][-1] == "trace_quality"
    tq = schema_eval["properties"]["trace_quality"]
    assert tq["additionalProperties"] is False
    assert tq["properties"]["task_understanding"]["enum"] == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_flat_rubric_raises_value_error(tmp_path):
    """flat 格式 rubric 无法构建 prompts（QueryRubric.model_validate 抛 ValueError）。"""
    config = TaskConfig(
        id="f1",
        prompt="p",
        rubric=[{"completion_rubric": "做A", "quality_rubric": {"1.0": "好"}}],
    )
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    with pytest.raises(ValueError):
        build_prompts(config, False, task_dir, result_dir)


def test_render_tree_connectors():
    group = RubricNode(
        id="OR-BC",
        type="group",
        combinator="or",
        name="会议冲突处理与提醒创建",
        children=[
            RubricNode(id="B", type="leaf", name="处理了会议冲突"),
            RubricNode(id="C", type="leaf", name="创建了提醒"),
        ],
    )
    text = "\n".join(_render_tree(group))
    assert text.startswith("✦ 会议冲突处理与提醒创建 [OR-BC] — OR 组")
    assert "├─ 处理了会议冲突 [B] — 叶子节点" in text
    assert "└─ 创建了提醒 [C] — 叶子节点" in text


def test_render_tree_top_leaf_weight():
    leaf = RubricNode(id="Q", type="leaf", name="输出规范")
    text = "\n".join(_render_tree(leaf, weight=3.0))
    assert text == "✦ 输出规范 [Q] — 叶子节点, 权重 3"
