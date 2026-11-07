"""结果分析（core/display/export）。

CLI 入口 `analyze_results` 默认 `run_id="average"`，输出 `{result_dir}/analysis_report.xlsx`。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.analyzer.core import (
    calculate_statistics,
    load_all_results_multi,
    load_task_configs,
    merge_task_data,
)
from src.analyzer.export import export_multi_run_to_excel, export_results_to_excel
from src.runs import list_model_runs


def analyze_results(
    result_dir: str | Path,
    tasks_dir: str | Path | None = None,
    run_id: str = "average",
    output_path: str | Path | None = None,
) -> Path:
    """分析既有结果并导出 Excel。默认 `run_id="average"`，
    输出 `{result_dir}/analysis_report.xlsx`；多轮（max_run > 1）时导出多轮工作簿。
    """
    result_dir = Path(result_dir)
    output_path = Path(output_path) if output_path else result_dir / "analysis_report.xlsx"
    if run_id == "average" and list_model_runs(result_dir)["max_run"] > 1:
        export_multi_run_to_excel(result_dir, output_path, tasks_dir)
        return output_path
    scores = load_all_results_multi(result_dir, run_id)
    configs = load_task_configs(tasks_dir) if tasks_dir else {}
    task_data = merge_task_data(scores, configs)
    export_results_to_excel(task_data, output_path)
    return output_path


def analyze_and_print(
    result_dir: str | Path,
    tasks_dir: str | Path | None = None,
    run_id: str = "average",
) -> dict[str, Any]:
    """分析并打印到控制台（CLI `analyze`/`run` 命令用），返回统计结果。"""
    from src.analyzer.display import print_group_table, print_statistics, print_task_table

    result_dir = Path(result_dir)
    scores = load_all_results_multi(result_dir, run_id)
    configs = load_task_configs(tasks_dir) if tasks_dir else {}
    task_data = merge_task_data(scores, configs)
    stats = calculate_statistics(task_data)
    print_statistics(stats)
    print_group_table(stats["by_dimension"])
    print_task_table(task_data)
    return stats


__all__ = [
    "analyze_results",
    "analyze_and_print",
    "calculate_statistics",
    "load_all_results_multi",
    "load_task_configs",
    "merge_task_data",
    "export_results_to_excel",
    "export_multi_run_to_excel",
]
