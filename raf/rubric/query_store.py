"""Query 集中管理：queries.json 存储 + Excel 导入导出 + 数据迁移。"""
from __future__ import annotations

import io
import json
import threading
from pathlib import Path

from openpyxl import Workbook, load_workbook

from .models import QueryItem, now_iso

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
QUERIES_FILE = DATA_DIR / "queries.json"

_lock = threading.RLock()


def _read() -> list[dict]:
    if not QUERIES_FILE.exists():
        return []
    try:
        data = json.loads(QUERIES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(items: list[dict]) -> None:
    with _lock:
        tmp = QUERIES_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(QUERIES_FILE)


def list_queries() -> list[QueryItem]:
    with _lock:
        return [QueryItem(**q) for q in _read()]


def get_query(query_id: str) -> QueryItem | None:
    with _lock:
        for q in _read():
            if q.get("id") == query_id:
                return QueryItem(**q)
    return None


def find_query_by_text(text: str) -> QueryItem | None:
    """按文本精确匹配（忽略首尾空白），导入去重用。"""
    needle = (text or "").strip()
    with _lock:
        for q in _read():
            if q.get("text", "").strip() == needle:
                return QueryItem(**q)
    return None


def create_query(text: str, tags: list[str] | None = None) -> QueryItem:
    """创建 query（按 text 去重：已存在则返回已有项）。"""
    existing = find_query_by_text(text)
    if existing:
        return existing
    item = QueryItem(text=text.strip(), tags=tags or [])
    with _lock:
        items = _read()
        items.append(item.model_dump())
        _write(items)
    return item


def batch_create_query(texts: list[str]) -> tuple[list[QueryItem], int]:
    """批量创建（按 text 去重）。返回 (全部项, 新建数量)。"""
    created: list[QueryItem] = []
    with _lock:
        items = _read()
        existing_texts = {q.get("text", "").strip() for q in items}
        for text in texts:
            text = (text or "").strip()
            if not text or text in existing_texts:
                continue
            item = QueryItem(text=text)
            items.append(item.model_dump())
            existing_texts.add(text)
            created.append(item)
        if created:
            _write(items)
    return list_queries(), len(created)


def update_query(query_id: str, text: str | None = None, tags: list[str] | None = None) -> QueryItem | None:
    with _lock:
        items = _read()
        for i, q in enumerate(items):
            if q.get("id") == query_id:
                if text is not None:
                    q["text"] = text.strip()
                if tags is not None:
                    q["tags"] = tags
                q["updated_at"] = now_iso()
                _write(items)
                return QueryItem(**q)
    return None


def delete_query(query_id: str) -> bool:
    with _lock:
        items = _read()
        kept = [q for q in items if q.get("id") != query_id]
        if len(kept) == len(items):
            return False
        _write(kept)
        return True


def rubric_reference_count(query_id: str) -> int:
    """引用该 query 的 rubric 数量（删除前检查）。"""
    from .storage import list_rubrics
    return sum(1 for r in list_rubrics() if r.get("query_id") == query_id)


# ---------- Excel 导入导出（列：id/text/tags） ----------

def export_excel() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "queries"
    ws.append(["id", "text", "tags"])
    for q in list_queries():
        ws.append([q.id, q.text, ",".join(q.tags)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def import_excel(data: bytes) -> tuple[list[QueryItem], int]:
    """解析 Excel（首行为表头 id/text/tags），按 text 去重后创建。"""
    wb = load_workbook(io.BytesIO(data), read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return list_queries(), 0
    texts: list[str] = []
    tags_map: dict[str, list[str]] = {}
    for row in rows[1:]:
        if not row or not row[1]:
            continue
        text = str(row[1]).strip()
        if not text or text in tags_map:
            continue
        texts.append(text)
        tags_map[text] = []
        if len(row) > 2 and row[2]:
            for t in str(row[2]).replace("，", ",").split(","):
                t = t.strip()
                if t and t not in tags_map[text]:
                    tags_map[text].append(t)
    for text in texts:
        create_query(text, tags_map[text])
    return list_queries(), len(texts)


# ---------- 数据迁移 ----------

def migrate_from_rubrics() -> dict:
    """从 rubrics.json 提取唯一 query 建 QueryItem 并回填 query_id。"""
    from .storage import RUBRICS_FILE, backfill_query_ids
    rubrics = []
    if RUBRICS_FILE.exists():
        try:
            data = json.loads(RUBRICS_FILE.read_text(encoding="utf-8"))
            rubrics = data if isinstance(data, list) else []
        except Exception:
            rubrics = []
    mapping: dict[str, str] = {}
    for r in rubrics:
        text = (r.get("query") or "").strip()
        if not text:
            continue
        item = find_query_by_text(text) or create_query(text)
        mapping[r.get("id", "")] = item.id
    updated = backfill_query_ids(mapping)
    return {"query_count": len(list_queries()), "updated_rubrics": updated}
