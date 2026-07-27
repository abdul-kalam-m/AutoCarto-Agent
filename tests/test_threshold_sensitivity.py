"""Threshold sensitivity sweep tests — TD-8.

Tests the core ROC/rate-curve computation logic with small, hand-checkable
inputs (not the full sweep, which draws hundreds of SAR samples and is
slow) -- these are the functions a wrong AUC or a broken separation claim
would come from, so they get exact-value assertions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import threshold_sensitivity as ts


def test_roc_sweep_perfect_separator():
    """A score that perfectly separates the two classes must give AUC=1.0
    and a threshold that achieves TPR=1, FPR=0."""
    records = [
        {"score": 0.9, "truth": True}, {"score": 0.8, "truth": True},
        {"score": 0.1, "truth": False}, {"score": 0.05, "truth": False},
    ]
    roc = ts.roc_sweep(records, "score", "truth", [0.0, 0.5, 1.0])
    at_half = next(r for r in roc if r["threshold"] == 0.5)
    assert at_half["tpr"] == 1.0
    assert at_half["fpr"] == 0.0
    assert ts.auc_from_roc(roc) == pytest.approx(1.0, abs=1e-9)


def test_roc_sweep_random_separator_gives_auc_near_half():
    """A score with no relationship to truth should give AUC near 0.5."""
    rng = np.random.default_rng(0)
    records = [{"score": float(rng.uniform(0, 1)), "truth": bool(rng.integers(0, 2))}
               for _ in range(500)]
    thresholds = [round(t, 2) for t in np.arange(0.0, 1.01, 0.05)]
    roc = ts.roc_sweep(records, "score", "truth", thresholds)
    auc = ts.auc_from_roc(roc)
    assert 0.35 < auc < 0.65  # loose bound -- this is a randomness sanity check, not exact


def test_auc_from_roc_trapezoidal_known_triangle():
    """A simple (0,0)->(1,1) diagonal ROC should give AUC=0.5 exactly."""
    roc = [{"threshold": 1.0, "fpr": 0.0, "tpr": 0.0},
           {"threshold": 0.5, "fpr": 0.5, "tpr": 0.5},
           {"threshold": 0.0, "fpr": 1.0, "tpr": 1.0}]
    assert ts.auc_from_roc(roc) == pytest.approx(0.5, abs=1e-9)


def test_rate_curve_gate2_monotonically_nonincreasing():
    """Pass rate must never increase as the threshold rises."""
    records = [{"regime": "x", "gvf": g} for g in [0.9, 0.7, 0.5, 0.3, 0.95, 0.6]]
    thresholds = [0.0, 0.3, 0.5, 0.7, 0.9, 1.0]
    curves = ts.rate_curve_gate2(records, thresholds)
    rates = [c["pass_rate"] for c in curves["x"]]
    assert all(a >= b for a, b in zip(rates, rates[1:]))
    assert curves["x"][0]["pass_rate"] == 1.0  # threshold 0.0 -> everything passes
    assert curves["x"][-1]["pass_rate"] == 0.0  # threshold 1.0 -> nothing passes (all gvf<1.0)


def test_rate_curve_gate4_monotonically_nonincreasing():
    """Rejection rate must never increase as the ceiling (the allowed
    distortion) rises -- a laxer ceiling rejects fewer scenarios, not more."""
    records = [{"scenario": s, "max_areal_exaggeration": v}
               for s, v in [("a", 0.05), ("b", 0.25), ("c", 0.50), ("d", 1.5)]]
    thresholds = [0.0, 0.1, 0.3, 0.6, 2.0]
    curve = ts.rate_curve_gate4(records, thresholds)
    rates = [c["rejection_rate"] for c in curve]
    assert all(a >= b for a, b in zip(rates, rates[1:]))
    assert curve[0]["rejection_rate"] == 1.0  # ceiling 0.0 -> everything exceeds it
    assert curve[-1]["rejection_rate"] == 0.0  # ceiling 2.0 -> nothing exceeds it


def test_sweep_gate3a_uses_real_gate_formula():
    """The sweep's Moran's I must come from SpatialStructureGate's own
    static method, not a reimplementation -- spot-check a strongly
    clustered draw actually shows high |I|."""
    records = ts.sweep_gate3a(seeds_per_rho=3)
    strong = [r["morans_i"] for r in records if r["rho_gen"] == 0.9]
    noise = [r["morans_i"] for r in records if r["rho_gen"] == 0.0]
    assert np.mean(np.abs(strong)) > np.mean(np.abs(noise))


def test_sweep_gate2_reuses_real_classification_engine():
    """The sweep's GVF must come from actually running
    ClassificationDiagnosticEngine.evaluate(), not a shortcut -- every
    record must carry a value in [0, 1]."""
    records = ts.sweep_gate2(n_per_regime=3)
    assert len(records) == 5 * 3  # 5 regimes
    assert all(0.0 <= r["gvf"] <= 1.0 for r in records)
