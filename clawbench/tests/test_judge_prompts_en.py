"""英文裁判 prompt 选择测试。"""

from __future__ import annotations

from src.agent_scorer.prompt_builder import build_system_prompt, build_user_prompt
from src.rubric.models import QueryRubric


def _rubric() -> QueryRubric:
    return QueryRubric.model_validate(
        {
            "query": "Do the task",
            "completion_rubric": [
                {"id": "c1", "type": "leaf", "name": "Read the input file",
                 "combinator": "and", "children": [], "tags": ["Tool Usage"]},
            ],
            "quality_rubric": [
                {"weight": 2, "node": {"id": "q1", "type": "leaf", "name": "Output is usable",
                                       "combinator": "and", "children": [], "tags": ["Tool Usage"]}},
            ],
        }
    )


def test_english_system_prompt_uses_english_sections():
    prompt = build_system_prompt(_rubric(), evaluate_trace=False, lang="en")
    assert "Evaluation Workflow" in prompt
    assert "Deliverable Inspection Protocol" in prompt
    assert "评估工作流" not in prompt


def test_english_user_prompt_labels():
    rubric = _rubric()
    user = build_user_prompt(
        "Do the task", "tasks/x", "results/x/run_1",
        "Completion tree", "Quality tree", None, lang="en",
    )
    assert "## Original Task Query" in user
    assert "## Task Directory" in user
    assert "## Rubric Evaluation Criteria" in user
    assert "原始任务提问" not in user


def test_chinese_user_prompt_still_chinese():
    rubric = _rubric()
    user = build_user_prompt(
        "做这个任务", "tasks/x", "results/x/run_1",
        "完成树", "质量树", None, lang="zh",
    )
    assert "## 原始任务提问" in user
    assert "## Rubric 评分标准" in user
