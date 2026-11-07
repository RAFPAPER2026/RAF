"""trace_meta 测试：UTC+8 锚点、搜索不截断、工具 detail、降级路径。"""

import json

from src.agent_scorer.trace_meta import extract_trace_meta


def _write_sessions(tmp_path, events):
    (tmp_path / "sessions.json").write_text(
        json.dumps({"container": "c", "sessions": events}, ensure_ascii=False),
        encoding="utf-8",
    )


def _tool_use(name, input_data, ts):
    return {"type": "assistant", "content": [{"type": "tool_use", "name": name, "input": input_data}], "timestamp": ts}


def _tool_result(content, ts, is_error=False):
    return {"type": "toolresult", "content": [{"type": "tool_result", "content": content, "is_error": is_error}], "timestamp": ts}


def test_utc8_anchor(tmp_path):
    """执行日期锚点：首条用户消息时间戳转 UTC+8（权威基准）。"""
    _write_sessions(
        tmp_path,
        [
            {"type": "user", "content": [{"type": "text", "text": "hi"}], "timestamp": "2026-07-04T02:00:00+00:00"},
            {"type": "assistant", "content": [{"type": "text", "text": "ok"}], "timestamp": "2026-07-04T02:30:00+00:00"},
        ],
    )
    meta = extract_trace_meta(tmp_path)
    assert meta.available is True
    assert "2026-07-04 10:00" in meta.execution_date_cn  # UTC 02:00 → UTC+8 10:00
    assert meta.api_calls == 1
    assert meta.duration_seconds == 1800.0


def test_search_query_never_truncated(tmp_path):
    long_query = "搜索关键词" * 100  # 500 字符
    _write_sessions(
        tmp_path,
        [
            {"type": "user", "content": [{"type": "text", "text": "hi"}], "timestamp": "2026-07-04T00:00:00+00:00"},
            _tool_use("web_search", {"query": long_query}, "2026-07-04T00:01:00+00:00"),
            _tool_result("结果", "2026-07-04T00:02:00+00:00"),
        ],
    )
    meta = extract_trace_meta(tmp_path)
    call = meta.tool_calls[0]
    assert call.is_search is True
    assert call.query == long_query  # 完整 query，永不截断
    assert call.success is True


def test_tool_detail_truncated(tmp_path):
    long_command = "echo " + "x" * 500
    _write_sessions(
        tmp_path,
        [
            {"type": "user", "content": [{"type": "text", "text": "hi"}], "timestamp": "2026-07-04T00:00:00+00:00"},
            _tool_use("exec", {"command": long_command}, "2026-07-04T00:01:00+00:00"),
            _tool_result("ok", "2026-07-04T00:02:00+00:00"),
        ],
    )
    meta = extract_trace_meta(tmp_path)
    call = meta.tool_calls[0]
    assert call.is_search is False
    assert len(call.detail) == 200 + 1  # 截断 _MAX_DETAIL_LEN=200 + 省略号
    assert call.detail.endswith("…")


def test_exec_search_skill_detected(tmp_path):
    """exec 命令匹配 skills/*search* 或显式集合视为搜索类。"""
    _write_sessions(
        tmp_path,
        [
            {"type": "user", "content": [{"type": "text", "text": "hi"}], "timestamp": "2026-07-04T00:00:00+00:00"},
            _tool_use("exec", {"command": 'python skills/web-search/main.py "机票" --date 2026-07-05'}, "2026-07-04T00:01:00+00:00"),
            _tool_use("exec", {"command": "baidu-search --query 航班"}, "2026-07-04T00:03:00+00:00"),
            _tool_result("ok", "2026-07-04T00:04:00+00:00"),
        ],
    )
    meta = extract_trace_meta(tmp_path)
    assert meta.tool_calls[0].is_search is True  # skills/web-search
    assert meta.tool_calls[1].is_search is True  # baidu-search
    assert "2026-07-05" in meta.tool_calls[0].query


def test_tool_success_paired_by_appearance_order(tmp_path):
    """工具成功与否按出现顺序与 toolResult 配对（非按 toolCallId）。"""
    _write_sessions(
        tmp_path,
        [
            {"type": "user", "content": [{"type": "text", "text": "hi"}], "timestamp": "2026-07-04T00:00:00+00:00"},
            _tool_use("exec", {"command": "good"}, "2026-07-04T00:01:00+00:00"),
            _tool_use("exec", {"command": "bad"}, "2026-07-04T00:02:00+00:00"),
            _tool_result("ok", "2026-07-04T00:03:00+00:00"),
            _tool_result("Error: boom", "2026-07-04T00:04:00+00:00", is_error=True),
        ],
    )
    meta = extract_trace_meta(tmp_path)
    assert [c.success for c in meta.tool_calls] == [True, False]


def _openclaw_message(role, content, ts, **msg_extra):
    """openclaw 原始会话记录形状（type==message + message 包裹）。"""
    return {
        "type": "message",
        "id": f"e_{role}",
        "timestamp": ts,
        "message": {"role": role, "content": content, **msg_extra},
    }


def test_raw_openclaw_records(tmp_path):
    """sessions.json 存 openclaw 完整原始记录时，trace_meta 归一后仍能提取锚点/工具/轮数。"""
    _write_sessions(
        tmp_path,
        [
            _openclaw_message("user", [{"type": "text", "text": "hi"}], "2026-07-04T02:00:00+00:00"),
            _openclaw_message(
                "assistant",
                [
                    {"type": "toolCall", "id": "c1", "name": "web_search",
                     "arguments": {"query": "航班 2026-07-05"}},
                    {"type": "text", "text": "最终答复"},
                ],
                "2026-07-04T02:10:00+00:00",
                usage={"input": 10, "output": 20},
            ),
            _openclaw_message(
                "toolResult",
                [{"type": "text", "text": "搜索结果"}],
                "2026-07-04T02:11:00+00:00",
                toolCallId="c1", toolName="web_search", isError=False,
            ),
        ],
    )
    meta = extract_trace_meta(tmp_path)
    assert meta.available is True
    assert "2026-07-04 10:00" in meta.execution_date_cn  # UTC 02:00 → UTC+8 10:00
    assert meta.api_calls == 1
    assert len(meta.tool_calls) == 1
    assert meta.tool_calls[0].is_search is True
    assert meta.tool_calls[0].query == "航班 2026-07-05"  # 搜索 query 不截断
    assert meta.tool_calls[0].success is True
    assert meta.duration_seconds == 660.0


def test_degradation_paths(tmp_path):
    # sessions.json 缺失 → None（prompt 整段省略）
    assert extract_trace_meta(tmp_path) is None
    # sessions 为空 → available=False（降级提示 judge 自行读 sessions.json）
    _write_sessions(tmp_path, [])
    meta = extract_trace_meta(tmp_path)
    assert meta is not None and meta.available is False
    # sessions.json 损坏 → None
    (tmp_path / "sessions.json").write_text("{broken", encoding="utf-8")
    assert extract_trace_meta(tmp_path) is None
