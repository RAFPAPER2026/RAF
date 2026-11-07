"""CLI 工具：对单条 query 调用 LLM 生成 rubric。

流程：构建 system prompt → chat_structured（失败 fallback chat_json，最多 3 次重试）
→ JSON 解析 → Pydantic 校验 → normalize → 叶子 tags 检查 → 保存。
"""
from __future__ import annotations

import argparse
import sys

from rubric.client import chat_json, chat_structured
from rubric.models import QueryRubricCreate, RubricNode, WeightedItem
from rubric.i18n import current_language, set_language
from rubric.prompt_modules import OUTPUT_SCHEMA, build_system_prompt, capability_names, get_active_version

MAX_RETRIES = 3


def generate_rubric(query: str, model: str | None = None,
                    prompt_version: str | None = None,
                    lang: str | None = None) -> QueryRubricCreate:
    """生成单条 rubric。返回未保存的 QueryRubricCreate（lang=en 时生成英文 rubric）。"""
    language = current_language(lang)
    version = prompt_version or get_active_version()
    system = build_system_prompt(version, language)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": query},
    ]
    data = None
    last_error: Exception | None = None
    for _attempt in range(MAX_RETRIES):
        # 优先结构化输出
        try:
            data = chat_structured(messages, OUTPUT_SCHEMA, model=model)
            break
        except Exception as exc:  # noqa: BLE001
            # 降级：普通 JSON 输出
            last_error = exc
            try:
                data = chat_json(messages, model=model)
                break
            except Exception as exc2:  # noqa: BLE001
                last_error = exc2
    if data is None:
        raise RuntimeError(f"生成失败（已重试 {MAX_RETRIES} 次）: {last_error}")

    rubric = QueryRubricCreate(
        query=query,
        prompt_version=version,
        language=language,
        completion_rubric=[RubricNode(**n) for n in data.get("completion_rubric", [])],
        quality_rubric=[
            WeightedItem(weight=item.get("weight", 1.0), node=RubricNode(**item["node"]))
            for item in data.get("quality_rubric", [])
        ],
    )
    normalize_rubric(rubric)
    check_leaf_tags(rubric)
    return rubric


def normalize_rubric(rubric: QueryRubricCreate) -> QueryRubricCreate:
    """规范化：单子 group 折叠、group tags 清空、去重子节点。"""
    rubric.completion_rubric = [_normalize_node(n) for n in rubric.completion_rubric]
    rubric.quality_rubric = [
        WeightedItem(weight=item.weight, node=_normalize_node(item.node)) for item in rubric.quality_rubric
    ]
    return rubric


def _normalize_node(node: RubricNode) -> RubricNode:
    node.tags = node.tags if node.type == "leaf" else []
    if node.type == "leaf":
        return node
    children = [_normalize_node(c) for c in node.children]
    # 单子 group 折叠：直接把子节点提升到父级
    if len(children) == 1:
        return children[0]
    # 去重子节点（按 name + type）
    seen: set[tuple] = set()
    deduped: list[RubricNode] = []
    for child in children:
        key = (child.name, child.type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(child)
    node.children = deduped
    return node


def check_leaf_tags(rubric: QueryRubricCreate) -> None:
    """无 tags 的叶子打印警告（不阻断）。"""
    names = set(capability_names())

    def _walk(nodes: list[RubricNode], path: str = "") -> None:
        for n in nodes:
            p = f"{path}/{n.name}" if path else n.name
            if n.type == "leaf":
                if not n.tags:
                    print(f"[warn] 叶子缺少 tags: {p}")
                else:
                    unknown = [t for t in n.tags if t not in names]
                    if unknown:
                        print(f"[warn] 叶子 tags 不在能力项列表: {p} -> {unknown}")
            else:
                _walk(n.children, p)

    _walk(rubric.completion_rubric)
    _walk([item.node for item in rubric.quality_rubric])


def main() -> None:
    parser = argparse.ArgumentParser(description="对单条 query 调用 LLM 生成 rubric")
    parser.add_argument("query", help="用户 query 文本")
    parser.add_argument("--prompt-version", default=None, help="使用的 prompt 版本（默认活跃版本）")
    parser.add_argument("--model", default=None, help="覆盖 llm_config 中的模型")
    parser.add_argument("--lang", choices=("zh", "en"), default="zh", help="生成语言（默认中文）")
    parser.add_argument("--no-save", action="store_true", help="只生成不保存")
    args = parser.parse_args()

    try:
        set_language(args.lang)
        rubric = generate_rubric(args.query, model=args.model, prompt_version=args.prompt_version, lang=args.lang)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] 生成失败: {exc}")
        sys.exit(1)

    if not args.no_save:
        from rubric.query_store import find_query_by_text
        from rubric.storage import create_rubric
        item = find_query_by_text(args.query)
        record = create_rubric(rubric, query_id=item.id if item else None)
        print(f"[ok] 已保存 rubric: {record['id']}（query_id={record.get('query_id') or '-'}）")
    print(rubric.model_dump_json(indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
