"""结果分析核心：统计、分组、通过判定。

`_is_passed` 与 `src/runs.py::_is_passed` 一致实现（complete_flag 优先 + 分数阈值回退）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from src.models import TaskConfig
from src.runs import is_passed, load_pass_threshold, synthesize_model_task_scores

# 与 src/runs.py::_is_passed 一致实现（同一函数，别名保持文档命名）
_is_passed = is_passed

# 主场景 primary_scenario 回退 scenario_category
GROUP_DIMENSIONS = {
    "primary_scenario": "主场景",
    "secondary_scenario": "次场景",
    "ability_category": "能力",
    "difficulty": "难度",
    "complexity": "复杂度",
}

COMPARISON_DIMENSIONS = tuple(GROUP_DIMENSIONS.keys())


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def load_all_results_multi(
    result_dir: str | Path, run_id: str = "average", trace_config: dict | None = None
) -> dict[str, dict]:
    """委托 `synthesize_model_task_scores`（"average" → 逐 case 平均、无 run 的 case 丢弃；
    具体 run → 读该 run 原始 score.json，缺该 run 的 case 跳过）。
    """
    return synthesize_model_task_scores(result_dir, run_id, trace_config)


def load_task_configs(tasks_dir: str | Path | None) -> dict[str, TaskConfig]:
    """tasks_dir 下各 case 的 config.json（task_name → TaskConfig）。"""
    configs: dict[str, TaskConfig] = {}
    if not tasks_dir:
        return configs
    tasks_dir = Path(tasks_dir)
    if not tasks_dir.is_dir():
        return configs
    for child in sorted(tasks_dir.iterdir()):
        if not child.is_dir() or not TaskConfig.config_path(child).is_file():
            continue
        try:
            configs[child.name] = TaskConfig.load(child)
        except (OSError, ValueError, TypeError):
            continue
    return configs


def merge_task_data(
    task_scores: dict[str, dict], configs: dict[str, TaskConfig] | None = None
) -> dict[str, dict]:
    """score dict 合并 config 分类字段（有 config 时 config 优先，score 回退）。"""
    configs = configs or {}
    merged: dict[str, dict] = {}
    for task_name, score in task_scores.items():
        entry = dict(score)
        entry["task_name"] = task_name
        cfg = configs.get(task_name)
        if cfg is not None:
            entry["task_id"] = cfg.id or entry.get("task_id") or task_name
            entry["verifier_type"] = cfg.verifier_type or entry.get("verifier_type") or "manual"
            if cfg.primary_scenario:
                entry["primary_scenario"] = cfg.primary_scenario
            elif cfg.scenario_category:
                entry["primary_scenario"] = cfg.scenario_category
            if cfg.secondary_scenario:
                entry["secondary_scenario"] = cfg.secondary_scenario
            if cfg.ability_category:
                entry["ability_category"] = list(cfg.ability_category)
            if cfg.difficulty:
                entry["difficulty"] = cfg.difficulty
            if cfg.complexity:
                entry["complexity"] = cfg.complexity
        else:
            entry["task_id"] = entry.get("task_id") or task_name
            entry.setdefault("verifier_type", "manual")
        merged[task_name] = entry
    return merged


def _iter_run_durations(score: dict) -> Iterable[float]:
    """多轮取 per-run 时长总和。"""
    runs = score.get("runs")
    if isinstance(runs, list):
        for run in runs:
            if isinstance(run, dict) and _is_number(run.get("duration")):
                yield float(run["duration"])
        return
    if _is_number(score.get("duration")):
        yield float(score["duration"])


def _group_by(task_data: dict[str, dict], dimension: str) -> dict[str, dict]:
    """分类统计：每类 `{count, avg_score, pass_rate}`；list 型 ability_category 分数计入每项。"""
    threshold = load_pass_threshold()
    groups: dict[str, dict[str, Any]] = {}

    def add(key: str, entry: dict) -> None:
        group = groups.setdefault(key, {"count": 0, "scores": [], "passed": 0})
        group["count"] += 1
        if _is_number(entry.get("score")):
            group["scores"].append(float(entry["score"]))
        if is_passed(entry, threshold):
            group["passed"] += 1

    for entry in task_data.values():
        if dimension == "ability_category":
            categories = entry.get("ability_category") or []
            if isinstance(categories, str):
                categories = [categories]
            for category in categories:
                add(str(category), entry)
            continue
        value = entry.get(dimension)
        if value is None or value == "":
            continue
        add(str(value), entry)

    result: dict[str, dict[str, Any]] = {}
    for key, group in groups.items():
        result[key] = {
            "count": group["count"],
            "avg_score": _mean(group["scores"]) if group["scores"] else None,
            "pass_rate": (group["passed"] / group["count"] * 100) if group["count"] else 0.0,
        }
    return result


def calculate_statistics(task_data: dict[str, dict]) -> dict:
    """统计输出：总/完成/失败任务数、总分（=average_score）、通过率、完成标记数、
    平均完成率、过程评价维度均值、token/成本/工具/API/错误恢复总量、总时长
    （多轮取 per-run 时长总和）、工具成功率、错误恢复率。
    """
    threshold = load_pass_threshold()
    entries = list(task_data.values())
    total = len(entries)
    completed = sum(1 for e in entries if e.get("status") == "completed")

    scores = [float(e["score"]) for e in entries if _is_number(e.get("score"))]
    average_score = _mean(scores) if scores else 0.0
    passed = sum(1 for e in entries if is_passed(e, threshold))
    completion_count = sum(1 for e in entries if e.get("complete_flag") == 1)
    completion_rates = [float(e["completion_rate"]) for e in entries if _is_number(e.get("completion_rate"))]

    dim_sums: dict[str, list[float]] = {}
    for e in entries:
        tq = e.get("trace_quality")
        if isinstance(tq, dict) and isinstance(tq.get("dimensions"), dict):
            for key, value in tq["dimensions"].items():
                if _is_number(value):
                    dim_sums.setdefault(str(key), []).append(float(value))

    def total_of(field: str) -> float:
        return sum(float(e[field]) for e in entries if _is_number(e.get(field)))

    tool_success = total_of("tool_success")
    tool_failed = total_of("tool_failed")
    judged = tool_success + tool_failed
    error_recoveries = total_of("error_recoveries")
    return {
        "total_tasks": total,
        "completed_tasks": completed,
        "failed_tasks": total - completed,
        "overall_score": round(average_score, 4),
        "average_score": round(average_score, 4),
        "pass_rate": round(passed / total * 100, 2) if total else 0.0,
        "completion_count": completion_count,
        "avg_completion_rate": round(_mean(completion_rates), 4) if completion_rates else 0.0,
        "avg_trace_dimensions": {
            key: round(_mean(values), 4) for key, values in dim_sums.items()
        },
        "total_duration": round(
            sum(d for e in entries for d in _iter_run_durations(e)), 2
        ),
        "total_input_tokens": total_of("input_tokens"),
        "total_output_tokens": total_of("output_tokens"),
        "total_input_cost": total_of("input_cost"),
        "total_output_cost": total_of("output_cost"),
        "total_cost": total_of("input_cost") + total_of("output_cost"),
        "total_tool_calls": total_of("tool_calls"),
        "total_tool_success": tool_success,
        "total_tool_failed": tool_failed,
        "overall_tool_success_rate": round(tool_success / judged * 100, 2) if judged else 0.0,
        "total_api_calls": total_of("api_calls"),
        "total_error_recoveries": error_recoveries,
        "overall_error_recovery_rate": (
            round(error_recoveries / tool_failed * 100, 2) if tool_failed else 0.0
        ),
        "by_dimension": {
            dimension: _group_by(task_data, dimension) for dimension in GROUP_DIMENSIONS
        },
    }


def _raw_complete_flag(entry: dict) -> int | None:
    """Excel 完成标记：complete_flag==1→1，==0→0，None/缺失→空。"""
    flag = entry.get("complete_flag")
    if flag == 1:
        return 1
    if flag == 0:
        return 0
    return None
