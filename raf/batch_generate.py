"""CLI 工具：批量生成 rubric。默认从 data/usecase/*.txt 读取 query 列表（每行一条）。"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
USECASE_DIR = DATA_DIR / "usecase"


def load_queries(input_file: str | None) -> list[str]:
    """读取 query 列表：--input 文件 > data/usecase/*.txt > queries.json。"""
    if input_file:
        return [line.strip() for line in Path(input_file).read_text(encoding="utf-8").splitlines() if line.strip()]
    if USECASE_DIR.exists():
        queries: list[str] = []
        for f in sorted(USECASE_DIR.glob("*.txt")):
            queries.extend(line.strip() for line in f.read_text(encoding="utf-8").splitlines() if line.strip())
        if queries:
            return queries
    from rubric.query_store import list_queries
    queries = [q.text for q in list_queries()]
    if not queries:
        raise SystemExit("未找到 query：请提供 --input 文件、data/usecase/*.txt，或先在 queries.json 中创建 query")
    return queries


def main() -> None:
    parser = argparse.ArgumentParser(description="批量生成 rubric")
    parser.add_argument("--input", default=None, help="query 列表文件（每行一条），默认 data/usecase/*.txt")
    parser.add_argument("--prompt-version", default=None, help="prompt 版本（默认活跃版本）")
    parser.add_argument("--concurrency", type=int, default=16, help="并发度（默认 16）")
    parser.add_argument("--lang", choices=("zh", "en"), default="zh", help="生成语言（默认中文）")
    args = parser.parse_args()

    from generate_rubric import generate_rubric
    from rubric.prompt_modules import get_active_version
    from rubric.query_store import find_query_by_text
    from rubric.i18n import current_language, set_language
    from rubric.storage import create_rubric, remove_by_query_version

    set_language(args.lang)
    version = args.prompt_version or get_active_version()
    queries = load_queries(args.input)
    print(f"共 {len(queries)} 条 query，prompt 版本 {version}，并发 {args.concurrency}")

    # 先删除同 (query, version) 旧数据，避免重复
    for q in queries:
        remove_by_query_version(q, version, current_language())

    succeeded = 0
    failed: list[tuple[str, str]] = []

    def _one(q: str):
        try:
            rubric = generate_rubric(q, prompt_version=version, lang=args.lang)
            item = find_query_by_text(q)
            create_rubric(rubric, query_id=item.id if item else None)
            return q, True, None
        except Exception as exc:  # noqa: BLE001
            return q, False, str(exc)

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        for q, ok, err in ex.map(_one, queries):
            if ok:
                succeeded += 1
                print(f"[ok]   {q[:60]}")
            else:
                failed.append((q, err))
                print(f"[error] {q[:60]} -> {err}")

    print(f"\n完成：成功 {succeeded}/{len(queries)}，失败 {len(failed)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
