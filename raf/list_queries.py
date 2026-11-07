"""CLI 工具：列出集中管理的 query。"""
from __future__ import annotations

import argparse
import sys

from rubric.query_store import list_queries
from rubric.storage import list_rubrics


def main() -> None:
    parser = argparse.ArgumentParser(description="列出 query")
    parser.add_argument("--search", default="", help="按文本过滤")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示 tags 与关联 rubric 数")
    args = parser.parse_args()

    rubric_counts: dict[str, int] = {}
    for r in list_rubrics():
        qid = r.get("query_id") or ""
        if qid:
            rubric_counts[qid] = rubric_counts.get(qid, 0) + 1

    total = 0
    for q in list_queries():
        if args.search and args.search not in q.text:
            continue
        total += 1
        if args.verbose:
            tags = ",".join(q.tags) if q.tags else "-"
            print(f"{q.id}\t{tags}\trubrics={rubric_counts.get(q.id, 0)}\t{q.text}")
        else:
            print(f"{q.id}\t{q.text}")
    print(f"\n共 {total} 条 query")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
