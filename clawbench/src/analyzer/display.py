"""控制台展示：统计总览、分类统计、任务明细。"""

from __future__ import annotations

from typing import Any

from src.analyzer.core import GROUP_DIMENSIONS


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def print_statistics(stats: dict) -> None:
    print("\n========== 总体统计 ==========")
    rows = [
        ("总任务数", stats["total_tasks"]),
        ("完成任务数", stats["completed_tasks"]),
        ("失败任务数", stats["failed_tasks"]),
        ("平均分", f"{stats['average_score']:.4f}"),
        ("通过率", f"{stats['pass_rate']:.2f}%"),
        ("平均完成率", f"{stats['avg_completion_rate']:.4f}"),
        ("总时长", format_duration(stats["total_duration"])),
        ("总输入Token", f"{stats['total_input_tokens']:.0f}"),
        ("总输出Token", f"{stats['total_output_tokens']:.0f}"),
        ("总成本", f"${stats['total_cost']:.4f}"),
        ("工具成功率", f"{stats['overall_tool_success_rate']:.2f}%"),
        ("错误恢复率", f"{stats['overall_error_recovery_rate']:.2f}%"),
        ("API调用次数", f"{stats['total_api_calls']:.0f}"),
    ]
    for label, value in rows:
        print(f"  {label:<12} {value}")
    for key, value in stats["avg_trace_dimensions"].items():
        print(f"  过程评价-{key:<8} {value:.4f}")


def print_group_table(by_dimension: dict[str, dict]) -> None:
    for dimension, label in GROUP_DIMENSIONS.items():
        groups = by_dimension.get(dimension) or {}
        if not groups:
            continue
        print(f"\n========== 分类统计（{label}） ==========")
        print(f"  {'分类值':<24}{'任务数':>6}{'平均分':>10}{'通过率(%)':>10}")
        for value, g in sorted(groups.items(), key=lambda kv: -kv[1]["count"]):
            avg = f"{g['avg_score']:.4f}" if g["avg_score"] is not None else "-"
            print(f"  {value:<24}{g['count']:>6}{avg:>10}{g['pass_rate']:>10.2f}")


def print_task_table(task_data: dict[str, dict]) -> None:
    print("\n========== 任务明细 ==========")
    entries = sorted(
        task_data.values(), key=lambda e: (str(e.get("task_id") or e["task_name"]))
    )
    print(f"  {'任务':<32}{'状态':<12}{'分数':>8}{'通过':>6}{'耗时':>10}")
    for entry in entries:
        score = f"{entry['score']:.4f}" if _is_number(entry.get("score")) else "-"
        passed = "✓" if entry.get("complete_flag") == 1 else "✗"
        print(
            f"  {str(entry.get('task_name'))[:32]:<32}{str(entry.get('status') or '-'):<12}"
            f"{score:>8}{passed:>6}{format_duration(entry.get('duration')):>10}"
        )
