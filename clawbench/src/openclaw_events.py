"""openclaw 容器会话转录（`~/.openclaw/agents/main/sessions/*.jsonl`）的读取与形状归一。

- **捞取存完整原始记录**：`read_openclaw_session_file` 逐行 `json.loads` 直接返回，
  不裁剪字段，使 `sessions.json` 的 `sessions[]` 保留「完整 jsonl」语义，
  不丢 session header / compaction / custom_message / system 角色 / 顶层元数据。
- **消费方归一**：`metrics.py` / `trace_meta.py` 等只做统计/摘要，
  需要 SDK 风格事件形状，用 `normalize_openclaw_events` 幂等归一：
  - 原始 message 记录 → SDK 事件（见 `convert_openclaw_events` 的字段映射）
  - 非 openclaw message 包裹的记录（已归一事件等）**原样返回**，不会二次转换丢失
- 单条字段映射（`convert_openclaw_events`，保留作底层工具/测试）：
  - 工具调用：`content[]` 里 `{"type":"toolCall","name":..,"arguments":{..}}` → `{"type":"tool_use","name":..,"input":{..}}`
  - 工具结果：`{"message":{"role":"toolResult",..}}` → `{"type":"tool_result","content","is_error",..}`
  - token：`message.usage.{input,output}` → 顶层 `event.usage.{input_tokens,output_tokens}`
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def _blocks_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts)


def _normalize_record(rec: dict) -> dict | None:
    """单条 openclaw JSONL 记录 → SDK 风格事件；非 message 包裹返回 None。"""
    if rec.get("type") != "message":
        return None
    msg = rec.get("message")
    if not isinstance(msg, dict):
        return None
    role = msg.get("role")
    content = msg.get("content")
    if not isinstance(content, list):
        content = [{"type": "text", "text": content}] if isinstance(content, str) else []
    blocks: list[dict] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "toolCall":
            blocks.append(
                {
                    "type": "tool_use",
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("arguments"),
                }
            )
        else:
            blocks.append(block)
    if role == "toolResult":
        return {
            "type": "tool_result",
            "id": rec.get("id"),
            "parentId": rec.get("parentId"),
            "timestamp": rec.get("timestamp"),
            "tool_use_id": msg.get("toolCallId"),
            "tool_name": msg.get("toolName"),
            "content": _blocks_to_text(msg.get("content")),
            "is_error": bool(msg.get("isError", False)),
        }
    if role not in ("user", "assistant"):
        return None
    event: dict[str, Any] = {
        "type": role,
        "content": blocks,
        "id": rec.get("id"),
        "parentId": rec.get("parentId"),
        "timestamp": rec.get("timestamp"),
    }
    usage = msg.get("usage")
    if isinstance(usage, dict):
        event["usage"] = {
            "input_tokens": usage.get(
                "input", usage.get("prompt_tokens", usage.get("input_tokens", 0))
            ),
            "output_tokens": usage.get(
                "output", usage.get("completion_tokens", usage.get("output_tokens", 0))
            ),
        }
    return event


def convert_openclaw_events(records: Iterable[dict]) -> list[dict]:
    """openclaw JSONL 行 → SDK 事件列表（丢弃非 message / 非 user·assistant·toolResult 行）。"""
    out: list[dict] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        event = _normalize_record(rec)
        if event is not None:
            out.append(event)
    return out


def normalize_openclaw_events(events: Iterable[Any]) -> list[Any]:
    """幂等归一：openclaw message 记录 → SDK 事件；其余记录原样返回。

    用于统计/摘要消费方在读取 `sessions.json`（已含完整原始记录）后、计算前归一，
    保证与原先「捞取即转换」路径的 token/工具统计一致、且不二次裁剪已归一事件。
    """
    out: list[Any] = []
    for rec in events:
        if isinstance(rec, dict):
            event = _normalize_record(rec)
            out.append(event if event is not None else rec)
        else:
            out.append(rec)
    return out


def read_openclaw_session_file(agents_dir: Path) -> list[dict]:
    """从 `{worker}/.openclaw_agents/main/sessions/` 读取最新会话转录的**完整原始记录**。

    逐行 `json.loads` 后直接返回（jsonl → `[]`），不做字段裁剪。
    返回空列表表示无可读会话。
    """
    sessions_dir = agents_dir / "main" / "sessions"
    if not sessions_dir.is_dir():
        return []
    # 排除 *.trajectory.jsonl：轨迹文件记录 session.started/model.completed/session.ended 等，
    # 以 session.ended 收尾、mtime 必然最新，但其中没有 type=="message" 的转录行，误选会导致空转录。
    jsonl_files = sorted(
        (p for p in sessions_dir.glob("*.jsonl") if not p.name.endswith(".trajectory.jsonl")),
        key=lambda p: p.stat().st_mtime,
    )
    if not jsonl_files:
        return []
    records: list[dict] = []
    for line in jsonl_files[-1].read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records
