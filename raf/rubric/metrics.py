"""一致性指标：Pearson r / Spearman ρ / QWK / Composite / 每 query 偏差。"""
from __future__ import annotations

import numpy as np
from scipy import stats

COMPOSITE_R_WEIGHT = 0.8
COMPOSITE_QWK_WEIGHT = 0.2


def discretize(scores: list[float], n_levels: int = 5) -> np.ndarray:
    """连续分数（0-1）离散化到 n 个等级（QWK 用）。"""
    arr = np.clip(np.asarray(scores, dtype=float), 0.0, 1.0)
    bins = np.linspace(0, 1, n_levels, endpoint=False)[1:]
    return np.digitize(arr, bins=bins).astype(int)


def quadratic_weighted_kappa(a: np.ndarray, b: np.ndarray, n_levels: int = 5) -> float:
    """二次权重 QWK：权重矩阵 w_ij = ((i - j) / (n_levels - 1))²。"""
    observed = np.zeros((n_levels, n_levels), dtype=float)
    for i, j in zip(a, b):
        observed[int(i), int(j)] += 1
    total = observed.sum()
    if total == 0:
        return 0.0
    expected = np.outer(observed.sum(axis=0), observed.sum(axis=1)) / total
    weights = np.array(
        [[((i - j) / (n_levels - 1)) ** 2 for j in range(n_levels)] for i in range(n_levels)],
        dtype=float,
    )
    return float(1.0 - (weights * observed).sum() / (weights * expected).sum())


def pearson(a, b) -> float | None:
    """Pearson r（排序一致性）。"""
    if len(a) < 2 or len(a) != len(b):
        return None
    r, _ = stats.pearsonr(a, b)
    return float(r)


def spearman(a, b) -> float | None:
    """Spearman ρ（秩相关）。"""
    if len(a) < 2 or len(a) != len(b):
        return None
    rho, _ = stats.spearmanr(a, b)
    return float(rho)


def compute_metrics(gold_scores: list[float], rater_means: list[float]) -> dict:
    """输入 gold 序列与评分者均值序列，返回指标字典。Composite = 0.8×r + 0.2×QWK。"""
    n = len(gold_scores)
    if n < 2:
        return {
            "n": n,
            "pearson_r": None,
            "spearman_rho": None,
            "qwk": None,
            "composite": None,
            "error": "至少需要 2 条 rubric 评分才能计算一致性指标；单 query 轮可直接点 RIFT 诊断走质量分支",
        }
    r = pearson(gold_scores, rater_means)
    rho = spearman(gold_scores, rater_means)
    qwk = quadratic_weighted_kappa(discretize(gold_scores), discretize(rater_means))
    composite = None
    if r is not None and qwk is not None:
        composite = COMPOSITE_R_WEIGHT * r + COMPOSITE_QWK_WEIGHT * qwk
    return {
        "n": n,
        "pearson_r": r,
        "spearman_rho": rho,
        "qwk": qwk,
        "composite": composite,
    }
