"""token/成本计算与工具调用统计。

工具调用与工具结果按**出现顺序**配对（镜像历史实现，非按 toolCallId）。
事件形状兼容 SDK 风格消息（`content` 为 block 列表）、简化 dict 与
openclaw 原始会话记录（`type=="message"` 包裹，经 `normalize_openclaw_events` 幂等归一）。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from src.openclaw_events import normalize_openclaw_events

# 每百万 token 价格（美元）：(输入, 输出)。默认不内置价格，成本记 0；
# 如需统计成本，在 configs/model_prices.json 中按 {"<model-substring>": [in, out]} 配置。
DEFAULT_PRICE_PER_MTOK = (0.0, 0.0)
_PRICE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "model_prices.json"
_PRICE_CACHE: dict[str, tuple[float, float]] | None = None


def _load_model_prices() -> dict[str, tuple[float, float]]:
    global _PRICE_CACHE
    if _PRICE_CACHE is not None:
        return _PRICE_CACHE
    path = Path(os.environ.get("CLAWBENCH_MODEL_PRICES", _PRICE_CONFIG_PATH))
    prices: dict[str, tuple[float, float]] = {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for name, value in (data or {}).items():
            if isinstance(value, dict):
                prices[str(name).lower()] = (
                    float(value.get("input", 0.0)), float(value.get("output", 0.0))
                )
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                prices[str(name).lower()] = (float(value[0]), float(value[1]))
    except (OSError, ValueError):
        pass
    _PRICE_CACHE = prices
    return prices

_ERROR_PREFIX = re.compile(r"^(error|exception|failed|traceback)", re.IGNORECASE)


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _content_blocks(event: dict) -> Iterable[Any]:
    """从事件中取出消息内容块（兼容 `content` 与 `message.content` 两种包裹）。"""
    content = event.get("content")
    if isinstance(content, list):
        yield from content
    message = event.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), list):
        yield from message["content"]


def iter_tool_uses(events: Iterable[Any]) -> Iterable[dict]:
    """按出现顺序产出工具调用（dict，含 `name`/`input`）。"""
    for event in events:
        if not isinstance(event, dict):
            continue
        for block in _content_blocks(event):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block
        for key in ("tool_use", "tool_call"):
            if isinstance(event.get(key), dict):
                yield event[key]
        if event.get("type") == "tool_use":
            yield event


def iter_tool_results(events: Iterable[Any]) -> Iterable[dict]:
    """按出现顺序产出工具结果。"""
    for event in events:
        if not isinstance(event, dict):
            continue
        for block in _content_blocks(event):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                yield block
        if isinstance(event.get("tool_result"), dict):
            yield event["tool_result"]
        if event.get("type") == "tool_result":
            yield event


def is_tool_result_success(result: Any) -> bool:
    """工具结果成功判定：优先 `is_error` 字段，其次内容错误前缀；无内容视为无错误信号。"""
    content: Any = result
    if isinstance(result, dict):
        if result.get("is_error") is not None:
            return not bool(result["is_error"])
        content = result.get("content")
    text = _as_text(content)
    if text is None or not text.strip():
        return True
    return not _ERROR_PREFIX.match(text.strip())


def pair_tool_calls_and_results(events: Iterable[Any]) -> list[tuple[dict | None, dict | None]]:
    """按出现顺序配对工具调用与结果（多出的单侧以 None 补齐）。"""
    uses = list(iter_tool_uses(events))
    results = list(iter_tool_results(events))
    pairs: list[tuple[dict | None, dict | None]] = []
    for i, use in enumerate(uses):
        pairs.append((use, results[i] if i < len(results) else None))
    for j in range(len(uses), len(results)):
        pairs.append((None, results[j]))
    return pairs


def count_api_calls(events: Iterable[Any]) -> int:
    """模型调用轮数 = assistant 消息数。"""
    n = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") == "assistant":
            n += 1
            continue
        message = event.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            n += 1
    return n


def estimate_tokens(text: str | None) -> int:
    return max(1, len(text) // 4) if text else 0


def calculate_tokens(events: Iterable[Any]) -> tuple[int, int]:
    """优先取事件中的显式 usage 字段，缺失时按文本长度估算。"""
    input_tokens = 0
    output_tokens = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        usage = event.get("usage")
        if isinstance(usage, dict):
            i = usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
            o = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
            input_tokens += int(i)
            output_tokens += int(o)
    if input_tokens == 0 and output_tokens == 0:
        first_user_text = ""
        assistant_text = ""
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("type") == "user" and not first_user_text:
                first_user_text = _as_text(event.get("content")) or ""
            if event.get("type") == "assistant":
                assistant_text += _as_text(event.get("content")) or ""
        input_tokens = estimate_tokens(first_user_text)
        output_tokens = estimate_tokens(assistant_text)
    return input_tokens, output_tokens


def price_per_mtok(model_name: str = "") -> tuple[float, float]:
    if not model_name:
        return DEFAULT_PRICE_PER_MTOK
    key = model_name.lower()
    for name, price in _load_model_prices().items():
        if name in key or key in name:
            return price
    return DEFAULT_PRICE_PER_MTOK


def calculate_cost(input_tokens: int, output_tokens: int, model_name: str = "") -> tuple[float, float]:
    pin, pout = price_per_mtok(model_name)
    return input_tokens / 1_000_000 * pin, output_tokens / 1_000_000 * pout


def _total_tool_duration(events: Iterable[Any]) -> float:
    """工具执行总时长（秒）：工具结果中 duration_ms / duration 字段求和。"""
    total = 0.0
    for result in iter_tool_results(events):
        if not isinstance(result, dict):
            continue
        if "duration_ms" in result:
            total += float(result["duration_ms"]) / 1000.0
        elif "duration" in result:
            try:
                total += float(result["duration"])
            except (TypeError, ValueError):
                pass
    return total


def calculate_metrics(events: Iterable[Any], model_name: str = "") -> dict:
    """从会话事件计算完整指标（runner 与转换器共用）。"""
    events = list(normalize_openclaw_events(events))
    input_tokens, output_tokens = calculate_tokens(events)
    input_cost, output_cost = calculate_cost(input_tokens, output_tokens, model_name)
    pairs = pair_tool_calls_and_results(events)
    uses = [use for use, _ in pairs if use is not None]
    tool_names = list(dict.fromkeys(use.get("name") or "unknown" for use in uses))
    outcomes: list[bool] = []
    for use, result in pairs:
        if use is None or result is None:
            continue
        outcomes.append(is_tool_result_success(result))
    tool_success = sum(outcomes)
    tool_failed = len(outcomes) - tool_success
    # 错误恢复：失败的工具调用之后（按顺序）出现过成功的工具调用
    failed_indices = [i for i, ok in enumerate(outcomes) if not ok]
    error_recoveries = sum(
        1 for idx in failed_indices if any(outcomes[j] for j in range(idx + 1, len(outcomes)))
    )
    judged = tool_success + tool_failed
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "tool_calls": len(uses),
        "tool_success": tool_success,
        "tool_failed": tool_failed,
        "tool_success_rate": (tool_success / judged) if judged else 0.0,
        "tool_names": tool_names,
        "error_recoveries": error_recoveries,
        "error_recovery_rate": (error_recoveries / tool_failed) if tool_failed else 0.0,
        "api_calls": count_api_calls(events),
        "task_time": round(_total_tool_duration(events), 3),
    }
