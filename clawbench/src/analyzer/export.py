"""分析统计与 Excel 导出（openpyxl）。

三个 sheet：
1. `任务汇总`：每任务一行；列含「完成标记」（_raw_complete_flag，1/0/空）、分数、时长、
   token/成本、工具、API、主/次场景、能力、难度、复杂度；有 tasks_dir 时含配置列；
   按 config `id`（或任务名）排序
2. `分类统计`：`[分类类型, 分类值, 任务数, 平均分, 通过率(%)]`，按数量降序
3. `总体统计`：`[指标, 值]`（总/完成/失败任务数、总分、平均分、时长、token、成本、
   工具成功率、错误恢复率、`过程评价-{维度名}` 行）

多轮导出（export_multi_run_to_excel）：先 `load_all_results_multi(run_id="average")` 平均统计
导出，再每 run 一个 `<run_id>` 任务汇总 sheet（per-run sheet 需完整 task_scores，无法从平均的
runs[] 重建，故逐 run 重读磁盘）；损坏 run 跳过不致命。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from src.analyzer.core import (
    GROUP_DIMENSIONS,
    _raw_complete_flag,
    calculate_statistics,
    load_all_results_multi,
    load_task_configs,
    merge_task_data,
)
from src.runs import list_model_runs, load_trace_config

SHEET_SUMMARY = "任务汇总"
SHEET_CATEGORIES = "分类统计"
SHEET_OVERALL = "总体统计"

# (score 字段, 中文列名)
SUMMARY_COLUMNS = [
    ("task_id", "任务ID"),
    ("task_name", "任务名称"),
    ("complete_flag", "完成标记"),
    ("score", "分数"),
    ("duration", "时长(秒)"),
    ("input_tokens", "输入Token"),
    ("output_tokens", "输出Token"),
    ("input_cost", "输入成本"),
    ("output_cost", "输出成本"),
    ("tool_calls", "工具调用"),
    ("tool_success", "工具成功"),
    ("tool_failed", "工具失败"),
    ("tool_success_rate", "工具成功率"),
    ("api_calls", "API调用"),
    ("error_recoveries", "错误恢复"),
    ("error_recovery_rate", "错误恢复率"),
    ("primary_scenario", "主场景"),
    ("secondary_scenario", "次场景"),
    ("ability_category", "能力"),
    ("difficulty", "难度"),
    ("complexity", "复杂度"),
]

# 有 tasks_dir 时附加的配置列
CONFIG_COLUMNS = [
    ("prompt", "任务描述"),
]

OVERALL_ROWS = [
    ("总任务数", "total_tasks"),
    ("完成任务数", "completed_tasks"),
    ("失败任务数", "failed_tasks"),
    ("总分", "overall_score"),
    ("平均分", "average_score"),
    ("通过率(%)", "pass_rate"),
    ("总时长(秒)", "total_duration"),
    ("总输入Token", "total_input_tokens"),
    ("总输出Token", "total_output_tokens"),
    ("总输入成本", "total_input_cost"),
    ("总输出成本", "total_output_cost"),
    ("总成本", "total_cost"),
    ("工具调用", "total_tool_calls"),
    ("工具成功", "total_tool_success"),
    ("工具失败", "total_tool_failed"),
    ("工具成功率(%)", "overall_tool_success_rate"),
    ("API调用次数", "total_api_calls"),
    ("错误恢复", "total_error_recoveries"),
    ("错误恢复率(%)", "overall_error_recovery_rate"),
    ("平均完成率", "avg_completion_rate"),
]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _style_header(ws) -> None:
    for cell in ws[1]:
        cell.font = Font(bold=True)


def _autofit(ws, max_width: int = 60) -> None:
    for column_cells in ws.columns:
        length = max(
            (len(str(cell.value)) if cell.value is not None else 0) for cell in column_cells
        )
        ws.column_dimensions[get_column_letter(column_cells[0].column)].width = min(
            max(length + 2, 10), max_width
        )


def _write_summary_sheet(workbook: Workbook, title: str, task_data: dict[str, dict]) -> None:
    if workbook.active.title == "Sheet" and title == SHEET_SUMMARY:
        ws = workbook.active
        ws.title = title
    else:
        ws = workbook.create_sheet(title)
    columns = list(SUMMARY_COLUMNS)
    if any("prompt" in e for e in task_data.values()):
        columns = SUMMARY_COLUMNS[:8] + CONFIG_COLUMNS + SUMMARY_COLUMNS[8:]
    ws.append([name for _, name in columns])
    _style_header(ws)
    entries = sorted(
        task_data.values(), key=lambda e: str(e.get("task_id") or e.get("task_name") or "")
    )
    for entry in entries:
        row: list[Any] = []
        for field, _ in columns:
            if field == "complete_flag":
                row.append(_raw_complete_flag(entry))
            elif field == "ability_category":
                categories = entry.get("ability_category")
                row.append(",".join(str(c) for c in categories) if categories else "")
            elif field == "prompt":
                prompt = entry.get("prompt")
                row.append(str(prompt)[:200] if prompt else "")
            elif field == "tool_success_rate":
                value = entry.get("tool_success_rate")
                row.append(round(float(value), 4) if _is_number(value) else None)
            else:
                row.append(entry.get(field))
        ws.append(row)
    _autofit(ws)


def _write_categories_sheet(workbook: Workbook, stats: dict) -> None:
    ws = workbook.create_sheet(SHEET_CATEGORIES)
    ws.append(["分类类型", "分类值", "任务数", "平均分", "通过率(%)"])
    _style_header(ws)
    rows: list[tuple[str, str, int, float | None, float]] = []
    for dimension, label in GROUP_DIMENSIONS.items():
        for value, g in (stats["by_dimension"].get(dimension) or {}).items():
            rows.append((label, value, g["count"], g["avg_score"], g["pass_rate"]))
    rows.sort(key=lambda r: -r[2])  # 按数量降序
    for row in rows:
        ws.append(list(row))
    _autofit(ws)


def _write_overall_sheet(workbook: Workbook, stats: dict, trace_config: dict | None = None) -> None:
    ws = workbook.create_sheet(SHEET_OVERALL)
    ws.append(["指标", "值"])
    _style_header(ws)
    for label, field in OVERALL_ROWS:
        ws.append([label, stats.get(field)])
    trace_config = trace_config if trace_config is not None else load_trace_config()
    dimension_names = {
        d.get("key"): d.get("name", d.get("key", ""))
        for d in trace_config.get("dimensions", [])
        if isinstance(d, dict)
    }
    for key, value in stats["avg_trace_dimensions"].items():
        name = dimension_names.get(key, key)
        ws.append([f"过程评价-{name}", round(value, 4)])
    _autofit(ws)


def export_results_to_excel(
    task_data: dict[str, dict], out_path: str | Path, trace_config: dict | None = None
) -> Path:
    """三 sheet Excel 报告。"""
    workbook = Workbook()
    stats = calculate_statistics(task_data)
    _write_summary_sheet(workbook, SHEET_SUMMARY, task_data)
    _write_categories_sheet(workbook, stats)
    _write_overall_sheet(workbook, stats, trace_config)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(out_path)
    return out_path


def export_multi_run_to_excel(
    result_dir: str | Path,
    out_path: str | Path,
    tasks_dir: str | Path | None = None,
    trace_config: dict | None = None,
) -> Path:
    """多轮工作簿：平均统计（三 sheet） + 每 run 一个 `<run_id>` 任务汇总 sheet。"""
    result_dir = Path(result_dir)
    trace_config = trace_config if trace_config is not None else load_trace_config()
    configs = load_task_configs(tasks_dir) if tasks_dir else {}

    workbook = Workbook()
    avg_scores = load_all_results_multi(result_dir, "average", trace_config)
    avg_data = merge_task_data(avg_scores, configs)
    stats = calculate_statistics(avg_data)
    _write_summary_sheet(workbook, SHEET_SUMMARY, avg_data)
    _write_categories_sheet(workbook, stats)
    _write_overall_sheet(workbook, stats, trace_config)

    for run_id in list_model_runs(result_dir)["runs"]:
        try:
            run_scores = load_all_results_multi(result_dir, run_id, trace_config)
        except (OSError, ValueError, TypeError):
            continue  # 损坏 run 跳过不致命
        run_data = merge_task_data(run_scores, configs)
        _write_summary_sheet(workbook, run_id, run_data)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(out_path)
    return out_path
