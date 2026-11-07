r"""extract_trace_meta() — sessions.json → prompt 元信息。

提取执行日期锚点（UTC+8）、起止/时长、api_calls、有序工具调用序列。
- 搜索/浏览类工具（及执行搜索类技能的 exec）展示完整 `query`（含日期锚点，永不截断）
- 其他工具展示 `detail`（命令/路径/首次编辑，截断 `_MAX_DETAIL_LEN=200`，多行负载由
  prompt_builder 缩进围栏包裹）
- 工具成功与否按**出现顺序**与 toolResult 配对（镜像 src/metrics.py，非按 toolCallId）
- exec 命令匹配 `skills/[\w-]*search[\w-]*` 或显式集合 `{baidu-search}` 视为搜索类
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from src.metrics import count_api_calls, is_tool_result_success, iter_tool_results, iter_tool_uses
from src.openclaw_events import normalize_openclaw_events

try:
    _CN_TZ = ZoneInfo("Asia/Shanghai")  # UTC+8
except Exception:  # noqa: BLE001 - 无 tzdata 时用固定偏移
    _CN_TZ = timezone(timedelta(hours=8))
_MAX_DETAIL_LEN = 200

SEARCH_TOOL_NAMES = {"web_search", "web_fetch", "browse", "browser", "search", "websearch"}
SEARCH_SKILL_EXECS = {"baidu-search"}
_SEARCH_SKILL_RE = re.compile(r"skills/[\w-]*search[\w-]*")

_DETAIL_KEYS = ("command", "file_path", "path", "url", "query")


@dataclass
class ToolCallMeta:
    name: str
    success: Optional[bool]  # True / False / None(unknown)
    query: Optional[str] = None  # 搜索类工具：完整 query（永不截断）
    detail: Optional[str] = None  # 其他工具：命令/路径/首次编辑
    is_search: bool = False


@dataclass
class TraceMeta:
    available: bool = False
    execution_date_cn: Optional[str] = None
    start_time_cn: Optional[str] = None
    end_time_cn: Optional[str] = None
    duration_seconds: Optional[float] = None
    api_calls: int = 0
    tool_calls: list[ToolCallMeta] = field(default_factory=list)


def _format_cn(dt: datetime) -> str:
    return dt.astimezone(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S") + "（UTC+8）"


def _parse_timestamp(value: Any) -> Optional[datetime]:
    """解析 ISO 时间戳（无时区视为 UTC）；支持 epoch 秒。"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _tool_input_text(tool_use: dict) -> str:
    """工具调用参数的可读文本（query/命令等）。"""
    inp = tool_use.get("input")
    if isinstance(inp, str):
        return inp
    if isinstance(inp, dict):
        for key in _DETAIL_KEYS:
            value = inp.get(key)
            if isinstance(value, str) and value:
                return value
        if inp:
            return json.dumps(inp, ensure_ascii=False)
    return ""


def _is_search_tool(name: str, input_text: str) -> bool:
    if name in SEARCH_TOOL_NAMES:
        return True
    if name in ("exec", "bash", "run"):
        if _SEARCH_SKILL_RE.search(input_text):
            return True
        for skill in SEARCH_SKILL_EXECS:
            if skill in input_text:
                return True
    return False


def _tool_detail(name: str, input_text: str) -> str:
    """非搜索工具：展示 command/路径/首次编辑（截断 200 字符）。"""
    text = input_text or ""
    return text[:_MAX_DETAIL_LEN] + ("…" if len(text) > _MAX_DETAIL_LEN else "")


def extract_trace_meta(result_dir: str | Path) -> Optional[TraceMeta]:
    """从 `{result_dir}/sessions.json` 提取执行轨迹元信息。

    - sessions.json 缺失/不可读 → None（prompt 整段省略）
    - 内容为空/无法解析 → `TraceMeta(available=False)`（降级提示 judge 自行读 sessions.json）
    """
    result_dir = Path(result_dir)
    sessions_path = result_dir / "sessions.json"
    if not sessions_path.is_file():
        return None
    try:
        data = json.loads(sessions_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    sessions = data.get("sessions") if isinstance(data, dict) else None
    if not isinstance(sessions, list) or not sessions:
        return TraceMeta(available=False)
    # sessions.json 现在存 openclaw 完整原始记录：先幂等归一为 SDK 事件再做统计
    sessions = normalize_openclaw_events(sessions)

    # 时间锚点：首条用户消息时间戳（权威基准，UTC+8）
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    for event in sessions:
        if isinstance(event, dict):
            ts = _parse_timestamp(event.get("timestamp"))
            if ts is not None:
                if start is None or ts < start:
                    start = ts
                if end is None or ts > end:
                    end = ts
    if start is None:
        return TraceMeta(available=False)

    uses = list(iter_tool_uses(sessions))
    results = list(iter_tool_results(sessions))
    tool_calls: list[ToolCallMeta] = []
    for i, use in enumerate(uses):
        name = str(use.get("name") or "unknown")
        input_text = _tool_input_text(use)
        is_search = _is_search_tool(name, input_text)
        success: Optional[bool] = None
        if i < len(results):
            success = is_tool_result_success(results[i])
        if is_search:
            tool_calls.append(
                ToolCallMeta(name=name, success=success, query=input_text, is_search=True)
            )
        else:
            tool_calls.append(
                ToolCallMeta(name=name, success=success, detail=_tool_detail(name, input_text))
            )

    duration = (end - start).total_seconds() if end is not None else None
    return TraceMeta(
        available=True,
        execution_date_cn=_format_cn(start),
        start_time_cn=_format_cn(start),
        end_time_cn=_format_cn(end) if end is not None else None,
        duration_seconds=duration,
        api_calls=count_api_calls(sessions),
        tool_calls=tool_calls,
    )
