"""flat → tree 迁移（**opt-in**，绝不自动运行）。

有损/退化：flat 无法表达 OR 分支与逐子权重，分档质量描述被丢弃；
迁移后的树分数与旧 flat 分数数值不一致（flat 平均 `completion * quality_score`，
tree 平均叶子通过与否）。
"""

from __future__ import annotations

from typing import Any

from src.rubric.models import QueryRubric, RubricNode, WeightedItem

FLAT_ROOT_ID = "node-flat-root"
FLAT_LEAF_PREFIX = "node-flat-"
FLAT_QUALITY_PREFIX = "node-flat-q-"
FLAT_QUALITY_WEIGHT = 3.0
FLAT_ROOT_NAME = "完成项"


def flat_rubric_to_tree(
    flat: Any,
    *,
    rubric_id: str = "",
    query: str = "",
    query_id: str = "",
    prompt_version: str = "",
) -> QueryRubric:
    """每个 flat 项 → 一个完成叶子（挂在顶层 AND 组 `node-flat-root`，名「完成项」，
    镜像「全部项须通过」）+ 一个质量叶子 `node-flat-q-{i:04d}`（weight 3.0）。
    """
    items = flat if isinstance(flat, list) else []
    completion_leaves: list[RubricNode] = []
    quality_items: list[WeightedItem] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        text = item.get("completion_rubric", "")
        if isinstance(text, dict):
            text = str(text)
        name = str(text).strip() or f"{FLAT_ROOT_NAME} {i + 1}"
        tags = item.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        tag_list = [str(t) for t in tags]
        completion_leaves.append(
            RubricNode(
                id=f"{FLAT_LEAF_PREFIX}{i:04d}",
                type="leaf",
                name=name,
                tags=tag_list,
            )
        )
        quality_items.append(
            WeightedItem(
                weight=FLAT_QUALITY_WEIGHT,
                node=RubricNode(
                    id=f"{FLAT_QUALITY_PREFIX}{i:04d}",
                    type="leaf",
                    name=name,
                    tags=tag_list,
                ),
            )
        )
    completion_rubric = (
        [
            RubricNode(
                id=FLAT_ROOT_ID,
                type="group",
                combinator="and",
                name=FLAT_ROOT_NAME,
                children=completion_leaves,
            )
        ]
        if completion_leaves
        else []
    )
    return QueryRubric(
        id=rubric_id,
        query=query,
        query_id=query_id,
        prompt_version=prompt_version,
        completion_rubric=completion_rubric,
        quality_rubric=quality_items,
    )
