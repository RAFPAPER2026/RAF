"""Rubric 与 Review 的文件型 JSON 存储（追加式，线程安全写锁）。"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from .models import QueryRubric, QueryRubricCreate, RubricReviewCreate, new_id

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RUBRICS_FILE = DATA_DIR / "rubrics.json"
REVIEWS_FILE = DATA_DIR / "reviews.json"

_lock = threading.RLock()


# ---------- 底层 JSON 读写 ----------

def _read_list(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_list(path: Path, data: list) -> None:
    with _lock:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


# ---------- Rubric ----------

def list_rubrics(search: str | None = None, limit: int | None = None,
                 offset: int | None = None, dedup: bool = False) -> list[dict]:
    """列出 rubric；dedup 时按 (query, prompt_version) 去重，保留最新。"""
    with _lock:
        items = [QueryRubric(**r).model_dump() for r in _read_list(RUBRICS_FILE)]
    if search:
        needle = search.lower()
        items = [r for r in items if needle in r["query"].lower()]
    if dedup:
        seen: dict[tuple, dict] = {}
        for r in items:
            seen[(r["query"], r["prompt_version"], r.get("language", "zh"))] = r  # 后者覆盖 → 保留最新
        items = list(seen.values())
    if offset:
        items = items[offset:]
    if limit is not None:
        items = items[:limit]
    return items


def get_rubric(rubric_id: str) -> dict | None:
    with _lock:
        for r in _read_list(RUBRICS_FILE):
            if r.get("id") == rubric_id:
                return QueryRubric(**r).model_dump()
    return None


def create_rubric(data: QueryRubricCreate, query_id: str | None = None) -> dict:
    """追加创建，返回完整记录。"""
    with _lock:
        items = _read_list(RUBRICS_FILE)
        record = data.model_dump()
        if query_id:
            record["query_id"] = query_id
        record["id"] = new_id("rubric")
        items.append(record)
        _write_list(RUBRICS_FILE, items)
    return record


def update_rubric(rubric_id: str, data: QueryRubricCreate) -> dict | None:
    """按 id 全量更新内容字段。"""
    with _lock:
        items = _read_list(RUBRICS_FILE)
        for i, r in enumerate(items):
            if r.get("id") == rubric_id:
                updated = data.model_dump()
                updated["id"] = rubric_id
                updated = QueryRubric(**updated).model_dump()
                items[i] = updated
                _write_list(RUBRICS_FILE, items)
                return updated
    return None


def delete_rubric(rubric_id: str) -> bool:
    with _lock:
        items = _read_list(RUBRICS_FILE)
        kept = [r for r in items if r.get("id") != rubric_id]
        if len(kept) == len(items):
            return False
        _write_list(RUBRICS_FILE, kept)
        return True


def remove_by_query_version(query: str, prompt_version: str, language: str | None = None) -> int:
    """删除同 (query, prompt_version, language) 的旧数据（批量生成前调用），返回删除条数。"""
    lang = language or "zh"
    with _lock:
        items = _read_list(RUBRICS_FILE)
        kept = [
            r for r in items
            if not (
                r.get("query") == query
                and r.get("prompt_version") == prompt_version
                and r.get("language", "zh") == lang
            )
        ]
        removed = len(items) - len(kept)
        if removed:
            _write_list(RUBRICS_FILE, kept)
        return removed


def cleanup_rubrics() -> int:
    """按 (query, prompt_version) 去重，保留最新，返回删除条数。"""
    with _lock:
        items = _read_list(RUBRICS_FILE)
        keep: list[dict] = []
        seen: set[tuple] = set()
        for r in reversed(items):
            key = (r.get("query", ""), r.get("prompt_version", ""), r.get("language", "zh"))
            if key in seen:
                continue
            seen.add(key)
            keep.append(r)
        keep.reverse()
        removed = len(items) - len(keep)
        if removed:
            _write_list(RUBRICS_FILE, keep)
        return removed


def list_rubrics_for_query_ids_version(query_ids: list[str], prompt_version: str) -> list[dict]:
    """列出指定 query 集合 + prompt 版本的 rubric（优化轮次用）。"""
    qids = set(query_ids)
    with _lock:
        return [
            QueryRubric(**r).model_dump()
            for r in _read_list(RUBRICS_FILE)
            if r.get("query_id") in qids and r.get("prompt_version") == prompt_version
        ]


def backfill_query_ids(mapping: dict[str, str]) -> int:
    """按 {rubric_id: query_id} 回填 query_id，返回更新条数。"""
    with _lock:
        items = _read_list(RUBRICS_FILE)
        updated = 0
        for r in items:
            rid = r.get("id")
            if rid in mapping and r.get("query_id") != mapping[rid]:
                r["query_id"] = mapping[rid]
                updated += 1
        if updated:
            _write_list(RUBRICS_FILE, items)
        return updated


# ---------- Review ----------

def list_reviews() -> list[dict]:
    with _lock:
        return list(_read_list(REVIEWS_FILE))


def list_reviews_for_rubric(rubric_id: str) -> list[dict]:
    with _lock:
        return [r for r in _read_list(REVIEWS_FILE) if r.get("rubric_id") == rubric_id]


def get_review_for_rubric(rubric_id: str) -> dict | None:
    """单条 rubric 的审核：取最近一次提交。"""
    reviews = list_reviews_for_rubric(rubric_id)
    return reviews[-1] if reviews else None


def create_review(data: RubricReviewCreate, prompt_version: str | None = None) -> dict:
    """提交审核（upsert：同一 rubric_id 覆盖旧记录）。"""
    with _lock:
        items = _read_list(REVIEWS_FILE)
        record = data.model_dump()
        if prompt_version:
            record["prompt_version"] = prompt_version
        items = [r for r in items if r.get("rubric_id") != record["rubric_id"]]
        items.append(record)
        _write_list(REVIEWS_FILE, items)
    return record


def review_stats() -> list[dict]:
    """按 prompt_version 聚合统计：平均分 + 分数分布。"""
    with _lock:
        reviews = _read_list(REVIEWS_FILE)
    grouped: dict[str, list[dict]] = {}
    for r in reviews:
        grouped.setdefault(r.get("prompt_version", ""), []).append(r)
    stats = []
    for version, rs in sorted(grouped.items()):
        stats.append({
            "prompt_version": version,
            "count": len(rs),
            "avg_completion": round(sum(r.get("completion_score", 0) for r in rs) / len(rs), 2),
            "avg_quality": round(sum(r.get("quality_score", 0) for r in rs) / len(rs), 2),
            "completion_distribution": _distribution([r.get("completion_score", 0) for r in rs]),
            "quality_distribution": _distribution([r.get("quality_score", 0) for r in rs]),
        })
    return stats


def _distribution(scores: list[int]) -> dict[str, int]:
    dist = {str(i): 0 for i in range(1, 6)}
    for s in scores:
        if 1 <= s <= 5:
            dist[str(s)] += 1
    return dist
