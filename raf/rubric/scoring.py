"""评分算法：completion 二元 + quality 加权。

两种质量分口径：
- ``paper``（默认，论文 Eq.1/Eq.2）：AND 组全过才得 1，否则 0；OR 组取 max；顶层加权平均。
- ``legacy_mean``（兼容旧实现）：AND 组取子节点均值（部分得分），OR 组取 max。

注意：前端 frontend/src/lib/scoring.ts 实现了相同逻辑（双份实现，修改需同步）。
"""
from __future__ import annotations

import os

from .models import RubricNode, WeightedItem

SCORING_MODES = ("paper", "legacy_mean")
_DEFAULT_MODE_ENV = "CLAWBENCH_SCORING_MODE"


def resolve_scoring_mode(mode: str | None = None) -> str:
    value = mode or os.environ.get(_DEFAULT_MODE_ENV) or "paper"
    if value not in SCORING_MODES:
        raise ValueError(f"unsupported scoring mode {value!r}; expected one of {SCORING_MODES}")
    return value


def evaluate_node(node: RubricNode, results: dict[str, bool]) -> bool:
    """按节点类型判定布尔值：
    - leaf：直接返回勾选状态（勾选 = True）
    - OR 组：任一子节点为真则整体为真（任一路径达成）
    - AND 组：全部子节点为真则整体为真（全部达成）
    """
    if node.type == "leaf":
        return bool(results.get(node.id, False))
    values = [evaluate_node(c, results) for c in node.children]
    if node.combinator == "or":
        return any(values)
    return all(values)


def evaluate_completion(nodes: list[RubricNode], results: dict[str, bool]) -> dict:
    """完成量规聚合：所有顶层项必须全部通过才算任务完成。"""
    item_results = {node.id: evaluate_node(node, results) for node in nodes}
    passed = sum(1 for v in item_results.values() if v)
    total = len(nodes)
    return {
        "completed": passed == total,
        "total": total,
        "passed": passed,
        "itemResults": item_results,
    }


def evaluate_node_score(
    node: RubricNode, results: dict[str, bool], scoring_mode: str | None = None
) -> float:
    """按节点类型返回 0-1 分数：
    - leaf：勾选 1.0，未勾选 0.0
    - OR 组：子节点分数最大值
    - AND 组：paper 口径全过才 1.0；legacy_mean 口径取子节点均值
    """
    mode = resolve_scoring_mode(scoring_mode)
    if node.type == "leaf":
        return 1.0 if results.get(node.id, False) else 0.0
    values = [evaluate_node_score(c, results, mode) for c in node.children]
    if not values:
        return 0.0
    if node.combinator == "or":
        return max(values)
    if mode == "paper":
        return 1.0 if all(v == 1.0 for v in values) else 0.0
    return sum(values) / len(values)


def score_quality(
    items: list[WeightedItem], results: dict[str, bool], scoring_mode: str | None = None
) -> dict:
    """质量量规加权聚合：score = Σ(weight_i × node_score_i) / Σ(weight_i)。"""
    mode = resolve_scoring_mode(scoring_mode)
    item_scores = [
        {"weight": item.weight, "nodeId": item.node.id,
         "score": evaluate_node_score(item.node, results, mode)}
        for item in items
    ]
    total_weight = sum(item.weight for item in items)
    weighted_completed = sum(item.weight * s["score"] for item, s in zip(items, item_scores))
    return {
        "weightedCompleted": weighted_completed,
        "totalWeight": total_weight,
        "score": weighted_completed / total_weight if total_weight else 0.0,
        "itemScores": item_scores,
        "scoringMode": mode,
    }


def collect_all_leaf_ids(nodes: list[RubricNode]) -> list[str]:
    """收集树中全部叶子 id（评分页勾选集合）。"""
    ids: list[str] = []
    for node in nodes:
        if node.type == "leaf":
            ids.append(node.id)
        else:
            ids.extend(collect_all_leaf_ids(node.children))
    return ids
