"""一致性指标测试（rubric/metrics.py）。"""

from __future__ import annotations

import pytest

from rubric.metrics import (
    COMPOSITE_QWK_WEIGHT,
    COMPOSITE_R_WEIGHT,
    compute_metrics,
    discretize,
    quadratic_weighted_kappa,
)


def test_identity_qwk_is_one():
    levels = discretize([0.1, 0.3, 0.5, 0.7, 0.9])
    assert quadratic_weighted_kappa(levels, levels) == pytest.approx(1.0)


def test_composite_weights():
    assert COMPOSITE_R_WEIGHT == 0.8
    assert COMPOSITE_QWK_WEIGHT == 0.2


def test_perfect_agreement_metrics():
    scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    result = compute_metrics(scores, scores)
    assert result["n"] == 9
    assert result["pearson_r"] == pytest.approx(1.0)
    assert result["spearman_rho"] == pytest.approx(1.0)
    assert result["qwk"] == pytest.approx(1.0)
    assert result["composite"] == pytest.approx(1.0)


def test_single_sample_reports_error():
    result = compute_metrics([0.5], [0.5])
    assert result["n"] == 1
    assert result["composite"] is None
    assert "error" in result
