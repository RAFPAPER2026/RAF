"""html2jsonl 转换器测试。"""

import base64
import json

import pytest

from manual_scorer.converters.html2jsonl import (
    export_to_jsonl,
    extract_openclaw_session,
)


def _session_html(payload: str) -> str:
    return (
        "<html><head><script id=\"session-data\">"
        f"{payload}"
        "</script></head><body></body></html>"
    )


def test_extract_plain_json(tmp_path):
    session = {"header": {"session_id": "s1"}, "entries": [{"type": "user", "text": "hi"}]}
    html = tmp_path / "s.html"
    html.write_text(_session_html(json.dumps(session)), encoding="utf-8")
    result = extract_openclaw_session(html)
    assert result["header"] == {"session_id": "s1"}
    assert result["entries"] == [{"type": "user", "text": "hi"}]


def test_extract_base64_payload(tmp_path):
    session = {"header": {"session_id": "s2"}, "entries": [{"type": "assistant", "text": "ok"}]}
    payload = base64.b64encode(json.dumps(session).encode("utf-8")).decode("ascii")
    html = tmp_path / "s.html"
    html.write_text(_session_html(payload), encoding="utf-8")
    result = extract_openclaw_session(html)
    assert result["header"] == {"session_id": "s2"}
    assert len(result["entries"]) == 1


def test_extract_missing_script_raises(tmp_path):
    html = tmp_path / "s.html"
    html.write_text("<html></html>", encoding="utf-8")
    with pytest.raises(ValueError, match="session-data"):
        extract_openclaw_session(html)


def test_export_to_jsonl(tmp_path):
    session = {"header": {"session_id": "s3"}, "entries": [{"type": "user", "text": "q"}]}
    html = tmp_path / "s.html"
    html.write_text(_session_html(json.dumps(session)), encoding="utf-8")
    out = tmp_path / "out.jsonl"
    export_to_jsonl(html, out)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["type"] == "header"
    assert first["session_id"] == "s3"
    assert json.loads(lines[1]) == {"type": "user", "text": "q"}
