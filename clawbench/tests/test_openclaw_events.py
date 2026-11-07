"""openclaw 会话转录读取/转换测试。"""

import json
import os

from src.openclaw_events import (
    convert_openclaw_events,
    normalize_openclaw_events,
    read_openclaw_session_file,
)


def _record(**kw) -> dict:
    d = {"type": "message", "id": "e1", "timestamp": "2026-09-01T00:00:00Z"}
    d.update(kw)
    return d


def _user(text: str) -> dict:
    return _record(message={"role": "user", "content": [{"type": "text", "text": text}]})


def _assistant_with_tool() -> dict:
    return _record(
        message={
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "..."},
                {
                    "type": "toolCall",
                    "id": "call_1",
                    "name": "write",
                    "arguments": {"path": "/root/Desktop/x.txt", "content": "hi"},
                },
            ],
            "usage": {"input": 25, "output": 123},
            "stopReason": "toolUse",
        }
    )


def _tool_result() -> dict:
    return _record(
        message={
            "role": "toolResult",
            "toolCallId": "call_1",
            "toolName": "write",
            "content": [{"type": "text", "text": "Successfully wrote 5 bytes"}],
            "isError": False,
        }
    )


def _system(text: str) -> dict:
    return _record(
        id="e0", timestamp="2026-09-01T00:00:00Z",
        message={"role": "system", "content": [{"type": "text", "text": text}]},
    )


def test_convert_user_and_assistant():
    events = convert_openclaw_events([_user("hi"), _assistant_with_tool()])
    assert events[0]["type"] == "user"
    assert events[0]["content"][0]["text"] == "hi"
    assert events[1]["type"] == "assistant"
    assert events[1]["usage"] == {"input_tokens": 25, "output_tokens": 123}


def test_convert_tool_call_block():
    events = convert_openclaw_events([_assistant_with_tool()])
    tool_blocks = [b for b in events[0]["content"] if b["type"] == "tool_use"]
    assert len(tool_blocks) == 1
    assert tool_blocks[0]["name"] == "write"
    assert tool_blocks[0]["input"] == {"path": "/root/Desktop/x.txt", "content": "hi"}


def test_convert_tool_result():
    events = convert_openclaw_events([_tool_result()])
    assert events[0]["type"] == "tool_result"
    assert events[0]["is_error"] is False
    assert "Successfully wrote" in events[0]["content"]
    assert events[0]["tool_name"] == "write"


def test_convert_drops_system_and_non_message():
    """转换（SDK 形状）丢弃 system 与非 message 行 —— 捞取存原始记录后由消费方归一。"""
    events = convert_openclaw_events(
        [_system("boot"), {"type": "compaction", "timestamp": "2026-09-01T00:00:00Z"}]
    )
    assert events == []


def test_metrics_compatible_on_converted(tmp_path):
    from src.metrics import calculate_metrics

    events = convert_openclaw_events([_user("hi"), _assistant_with_tool(), _tool_result()])
    m = calculate_metrics(events, model_name="deepseek-v4-flash")
    assert m["api_calls"] == 1
    assert m["tool_calls"] == 1
    assert m["tool_success"] == 1
    assert m["input_tokens"] == 25


def test_metrics_compatible_on_raw_records(tmp_path):
    """原始 openclaw 记录直接喂 metrics（sessions.json 完整存储路径）不回归。"""
    from src.metrics import calculate_metrics

    raw = [_user("hi"), _assistant_with_tool(), _tool_result()]
    m = calculate_metrics(raw, model_name="deepseek-v4-flash")
    assert m["api_calls"] == 1
    assert m["tool_calls"] == 1
    assert m["tool_success"] == 1
    assert m["tool_names"] == ["write"]
    assert m["input_tokens"] == 25
    assert m["output_tokens"] == 123


def test_normalize_is_idempotent():
    raw = [_user("hi"), _assistant_with_tool(), _tool_result(), _system("boot")]
    once = normalize_openclaw_events(raw)
    twice = normalize_openclaw_events(once)
    assert once == twice
    # openclaw message 记录被归一为 SDK 事件；无法归一的 role（system）原样保留（不丢信息）
    assert [e["type"] for e in once] == ["user", "assistant", "tool_result", "message"]
    assert once[3]["message"]["role"] == "system"


def _write_session(sdir, records):
    sdir.mkdir(parents=True)
    (sdir / "sess-1.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8",
    )


def test_read_openclaw_session_file_returns_raw_records(tmp_path):
    agents = tmp_path / ".openclaw_agents"
    _write_session(
        agents / "main" / "sessions",
        [_system("boot"), _user("hi"), _assistant_with_tool(), _tool_result()],
    )
    events = read_openclaw_session_file(agents)
    # 完整原始记录：不裁剪 system 行、保留 message 包裹与顶层元数据
    assert len(events) == 4
    assert events[0]["type"] == "message"
    assert events[0]["message"]["role"] == "system"
    assert events[1]["type"] == "message"
    assert events[1]["message"]["content"][0]["text"] == "hi"
    assert events[1]["id"] == "e1"
    assert events[3]["message"]["toolName"] == "write"


def test_read_skips_trajectory_file(tmp_path):
    """轨迹文件（{sessionId}.trajectory.jsonl）mtime 最新时不能被误选。"""
    agents = tmp_path / ".openclaw_agents"
    sdir = agents / "main" / "sessions"
    sdir.mkdir(parents=True)
    session = sdir / "sess-1.jsonl"
    session.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in [_user("hi")]),
        encoding="utf-8",
    )
    traj = sdir / "sess-1.trajectory.jsonl"
    traj.write_text(
        json.dumps(
            {"type": "session.ended", "sessionId": "sess-1", "timestamp": "2026-09-01T00:00:01Z"}
        ),
        encoding="utf-8",
    )
    # 复现竞态：trajectory 以 session.ended 收尾，是会话最后写入的文件
    os.utime(traj, (session.stat().st_mtime + 10,) * 2)
    events = read_openclaw_session_file(agents)
    assert len(events) == 1
    assert events[0]["type"] == "message"
    assert events[0]["message"]["role"] == "user"


def test_read_missing_dir_returns_empty(tmp_path):
    assert read_openclaw_session_file(tmp_path / "nope") == []
