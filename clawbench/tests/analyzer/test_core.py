"""分析统计测试（src/analyzer/core.py）。"""

import pytest

from src.analyzer.core import (
    _group_by,
    _iter_run_durations,
    _raw_complete_flag,
    calculate_statistics,
    merge_task_data,
)
from src.models import TaskConfig


def _sample_data():
    return {
        "t1": {
            "task_name": "t1",
            "status": "completed",
            "score": 1.0,
            "duration": 10,
            "complete_flag": 1,
            "completion_rate": 1.0,
            "input_tokens": 100,
            "output_tokens": 50,
            "input_cost": 0.1,
            "output_cost": 0.05,
            "tool_calls": 2,
            "tool_success": 2,
            "tool_failed": 0,
            "api_calls": 3,
            "error_recoveries": 0,
            "primary_scenario": "办公",
        },
        "t2": {
            "task_name": "t2",
            "status": "failed",
            "score": 0.5,
            "duration": 5,
            "complete_flag": 0,
            "completion_rate": 0.5,
            "input_tokens": 60,
            "output_tokens": 20,
            "input_cost": 0.02,
            "output_cost": 0.01,
            "tool_calls": 4,
            "tool_success": 1,
            "tool_failed": 3,
            "api_calls": 5,
            "error_recoveries": 1,
            "primary_scenario": "办公",
        },
    }


def test_calculate_statistics():
    stats = calculate_statistics(_sample_data())
    assert stats["total_tasks"] == 2
    assert stats["completed_tasks"] == 1
    assert stats["failed_tasks"] == 1
    assert stats["average_score"] == 0.75
    assert stats["overall_score"] == 0.75  # = average_score
    assert stats["pass_rate"] == 50.0
    assert stats["completion_count"] == 1
    assert stats["avg_completion_rate"] == 0.75
    assert stats["total_input_tokens"] == 160
    assert stats["total_output_tokens"] == 70
    assert stats["total_cost"] == pytest.approx(0.18)
    assert stats["total_duration"] == 15
    assert stats["overall_tool_success_rate"] == 50.0  # 成功 3 / 总计 6
    assert stats["total_api_calls"] == 8
    assert stats["total_error_recoveries"] == 1
    assert round(stats["overall_error_recovery_rate"], 2) == 33.33  # 1/3
    assert stats["by_dimension"]["primary_scenario"]["办公"]["count"] == 2


def test_group_by_ability_multi_count():
    data = {"t1": {"score": 1.0, "complete_flag": 1, "ability_category": ["A", "B"]}}
    groups = _group_by(data, "ability_category")
    assert groups["A"]["count"] == 1  # list 型 ability_category 分数计入每项
    assert groups["B"]["count"] == 1


def test_group_by_skips_missing():
    data = {"t1": {"score": 1.0}}
    assert _group_by(data, "difficulty") == {}


def test_iter_run_durations():
    single = {"duration": 10}
    assert list(_iter_run_durations(single)) == [10.0]
    multi = {"runs": [{"duration": 10}, {"duration": 20}, {"duration": None}]}
    assert list(_iter_run_durations(multi)) == [10.0, 20.0]  # 多轮取 per-run 时长总和


def test_raw_complete_flag():
    assert _raw_complete_flag({"complete_flag": 1}) == 1
    assert _raw_complete_flag({"complete_flag": 0}) == 0
    assert _raw_complete_flag({"complete_flag": None}) is None  # 空
    assert _raw_complete_flag({}) is None


def test_merge_task_data_config_priority():
    cfg = TaskConfig(
        id="cfg-id", prompt="p", verifier_type="manual",
        primary_scenario="主场景", difficulty="easy", ability_category=["X"],
    )
    merged = merge_task_data({"t": {"score": 0.5}}, {"t": cfg})
    assert merged["t"]["task_id"] == "cfg-id"
    assert merged["t"]["primary_scenario"] == "主场景"
    assert merged["t"]["difficulty"] == "easy"
    assert merged["t"]["score"] == 0.5  # score 保留


def test_merge_task_data_without_config():
    merged = merge_task_data({"t": {"score": 0.5}})
    assert merged["t"]["task_id"] == "t"
    assert merged["t"]["verifier_type"] == "manual"
