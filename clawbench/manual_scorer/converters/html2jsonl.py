"""html2jsonl：正则提取 `<script id="session-data">`，base64 解码 JSON 解析
→ `{header, entries}`；export_to_jsonl 写 `{"type":"header",...}` + 每 entry 一行。
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

_SESSION_SCRIPT_RE = re.compile(
    r'<script\s+id="session-data"[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE
)


def extract_openclaw_session(html_path: str | Path) -> dict:
    """从 Openclaw 会话 HTML 中提取 `{header, entries}`。"""
    text = Path(html_path).read_text(encoding="utf-8", errors="replace")
    match = _SESSION_SCRIPT_RE.search(text)
    if not match:
        raise ValueError(f'未找到 <script id="session-data">：{html_path}')
    payload = match.group(1).strip()
    data = None
    try:
        data = json.loads(payload)  # 直接 JSON
    except ValueError:
        try:
            decoded = base64.b64decode(payload)
            data = json.loads(decoded.decode("utf-8"))
        except (ValueError, OSError) as exc:
            raise ValueError(f"session-data 解析失败：{html_path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"session-data 内容异常：{html_path}")
    header = data.get("header") if isinstance(data.get("header"), dict) else {}
    entries = data.get("entries") if isinstance(data.get("entries"), list) else []
    return {"header": header, "entries": entries}


def export_to_jsonl(html_path: str | Path, out_path: str | Path) -> None:
    """导出会话为 JSONL：`{"type":"header",...}` + 每 entry 一行。"""
    session = extract_openclaw_session(html_path)
    lines = [json.dumps({"type": "header", **session["header"]}, ensure_ascii=False)]
    lines += [
        json.dumps(entry, ensure_ascii=False, default=str) for entry in session["entries"]
    ]
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
