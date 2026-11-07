"""Rubric 评分公式（纯逻辑，无 IO）。

两种质量分口径：
- ``paper``（默认，论文 Eq.1/Eq.2）：AND 组按二值聚合——所有子节点通过才得 1，否则 0；
  OR 组取 max；顶层按权重加权平均。
- ``legacy_mean``（兼容旧实现）：AND 组取子节点均值（部分得分），OR 组取 max。

完成度始终为二元：叶子 → 通过/未通过；组 or → any；组 and（默认）→ all；
空组 → all([]) == True；``completed`` = 所有顶层项全过；无项时 True。
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

from src.rubric.models import QueryRubric, RubricNode, WeightedItem

SCORING_MODES = ("paper", "legacy_mean")
_DEFAULT_MODE_ENV = "CLAWBENCH_SCORING_MODE"


def resolve_scoring_mode(mode: str | None = None) -> str:
    """解析评分口径：显式参数 > 环境变量 > paper。"""
    value = mode or os.environ.get(_DEFAULT_MODE_ENV) or "paper"
    if value not in SCORING_MODES:
        raise ValueError(f"unsupported scoring mode {value!r}; expected one of {SCORING_MODES}")
    return value


def _results_map(results: Any) -> Mapping[str, bool]:
    """兼容 `RubricResults` 对象与裸 dict。"""
    if isinstance(results, Mapping):
        return {str(k): bool(v) for k, v in results.items()}
    attr = getattr(results, "results", None)
    if isinstance(attr, Mapping):
        return {str(k): bool(v) for k, v in attr.items()}
    return {}


def _node_passed(node: RubricNode, results: Mapping[str, bool]) -> bool:
    if node.type == "leaf":
        return bool(results.get(node.id, False))
    if node.combinator == "or":
        return any(_node_passed(child, results) for child in node.children)
    return all(_node_passed(child, results) for child in node.children)  # 空组 all([]) == True


def _node_score(node: RubricNode, results: Mapping[str, bool], mode: str) -> float:
    if node.type == "leaf":
        return 1.0 if results.get(node.id, False) else 0.0
    if not node.children:
        return 0.0  # 空组：质量分显式 0.0（与完成度空组为真不同）
    if node.combinator == "or":
        return max(_node_score(child, results, mode) for child in node.children)
    if mode == "paper":
        # 论文口径：AND 组作为整体，全过为 1，否则为 0
        return 1.0 if all(_node_score(child, results, mode) == 1.0 for child in node.children) else 0.0
    scores = [_node_score(child, results, mode) for child in node.children]
    return sum(scores) / len(scores)  # legacy_mean：AND 组取均值


def _collect_leaves(nodes: Sequence[RubricNode]) -> list[RubricNode]:
    leaves: list[RubricNode] = []
    for node in nodes:
        if node.type == "leaf":
            leaves.append(node)
        else:
            leaves.extend(_collect_leaves(node.children))
    return leaves


def evaluate_completion(nodes: Sequence[RubricNode], results: Any) -> dict:
    """完成度（二元）。返回 `{completed, total, passed, item_results}`。

    `completed` = 所有顶层项全过（all-pass 二元）；无项时 `completed=True`。
    `total`/`passed` 按叶子统计。
    """
    m = _results_map(results)
    item_results = [
        {"id": node.id, "name": node.name, "passed": _node_passed(node, m)}
        for node in nodes
    ]
    leaves = _collect_leaves(nodes)
    passed = sum(1 for leaf in leaves if m.get(leaf.id, False))
    completed = all(_node_passed(node, m) for node in nodes)
    return {
        "completed": completed,
        "total": len(leaves),
        "passed": passed,
        "item_results": item_results,
    }


def score_quality(
    items: Sequence[WeightedItem],
    results: Any,
    scoring_mode: str | None = None,
) -> dict:
    """质量分（连续 0–1）。返回 `{weighted_completed, total_weight, score, item_scores, scoring_mode}`。

    顶层 `score = Σ(weight·score) / Σweight`；`quality_rubric` 为空 → 0.0。
    """
    mode = resolve_scoring_mode(scoring_mode)
    m = _results_map(results)
    item_scores = [
        {
            "id": item.node.id,
            "name": item.node.name,
            "weight": item.weight,
            "score": _node_score(item.node, m, mode),
        }
        for item in items
    ]
    weighted_completed = sum(it["weight"] * it["score"] for it in item_scores)
    total_weight = sum(it["weight"] for it in item_scores)
    score = weighted_completed / total_weight if total_weight > 0 else 0.0
    return {
        "weighted_completed": weighted_completed,
        "total_weight": total_weight,
        "score": score,
        "item_scores": item_scores,
        "scoring_mode": mode,
    }


def compute_rubric_score(
    rubric: QueryRubric,
    results: Any,
    scoring_mode: str | None = None,
) -> dict:
    """汇总评分（结果随原始 rubric_results 一并持久化，读取路径因此与格式无关）。

    返回键：completion / quality / quality_score / score / completion_rate / complete_flag /
    scoring_mode。
    """
    mode = resolve_scoring_mode(scoring_mode)
    completion = evaluate_completion(rubric.completion_rubric, results)
    quality = score_quality(rubric.quality_rubric, results, mode)
    quality_score = quality["score"]
    completion_rate = (
        completion["passed"] / completion["total"] if completion["total"] else 0.0
    )
    complete_flag = 1 if completion["completed"] else 0
    return {
        "completion": completion,
        "quality": quality,
        "quality_score": quality_score,
        "score": quality_score,
        "completion_rate": completion_rate,
        "complete_flag": complete_flag,
        "scoring_mode": mode,
    }


def collect_leaf_ids(rubric: QueryRubric) -> list[str]:
    """DFS 遍历 completion + quality 两树收集全部叶子 id（agent_scorer 枚举检查项用）。"""
    nodes: list[RubricNode] = list(rubric.completion_rubric) + [
        item.node for item in rubric.quality_rubric
    ]
    ids: list[str] = []
    seen: set[str] = set()
    for leaf in _collect_leaves(nodes):
        if leaf.id not in seen:
            seen.add(leaf.id)
            ids.append(leaf.id)
    return ids
