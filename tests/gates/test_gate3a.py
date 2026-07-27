"""Gate 3a (univariate Moran's I) behavioral tests — Blueprint §3.2 acceptance criteria."""

from __future__ import annotations

import libpysal
import numpy as np
import pytest
from scipy.linalg import solve

from autocarto.execution.gates.gate3a_spatial_autocorrelation import SpatialStructureGate


@pytest.fixture(scope="module")
def W():
    w = libpysal.weights.lat2W(10, 10)
    w.transform = "r"
    return w.full()[0]


def _sar_draw(W: np.ndarray, rho: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    A = np.eye(W.shape[0]) - rho * W
    eps = rng.standard_normal(W.shape[0])
    return solve(A, eps)


def test_sar_clustered_passes(W):
    x = _sar_draw(W, rho=0.8, seed=7)
    res = SpatialStructureGate().evaluate(x, W, permutations=199, random_state=0)
    assert res.decision == "PASS"
    assert res.diagnostics["morans_i"] > 0.15
    assert res.diagnostics["pattern"] == "clustered_positive"


def test_white_noise_rejected_with_proportional_symbol_prescription(W):
    rng = np.random.default_rng(99)
    x = rng.normal(size=W.shape[0])
    res = SpatialStructureGate().evaluate(x, W, permutations=199, random_state=0)
    assert res.decision == "REJECT"
    assert res.prescription.method == "proportional_symbol"


def test_checkerboard_negative_autocorrelation_passes_with_note(W):
    n = 10
    x = np.array([1.0 if (i + j) % 2 == 0 else -1.0 for i in range(n) for j in range(n)])
    res = SpatialStructureGate().evaluate(x, W, permutations=199, random_state=0)
    assert res.decision == "PASS"
    assert res.diagnostics["morans_i"] < -0.5
    assert res.diagnostics["pattern"] == "dispersed_negative"
    assert "DISPERSED" in res.instruction


def test_matches_esda_moran_exactly(W):
    esda = pytest.importorskip("esda")
    from libpysal.weights import W as PysalW

    x = _sar_draw(W, rho=0.6, seed=3)
    res = SpatialStructureGate().evaluate(x, W, permutations=0, random_state=0)

    w_obj = libpysal.weights.lat2W(10, 10)
    w_obj.transform = "r"
    m = esda.Moran(x, w_obj, permutations=0)
    # Gate diagnostics round to 4dp for trace legibility (Gate 2/3b convention).
    assert res.diagnostics["morans_i"] == pytest.approx(m.I, abs=1e-4)


def test_non_row_standardized_weights_raises(W):
    raw_binary = (W > 0).astype(float) * 4  # arbitrary non-1 row sums
    with pytest.raises(ValueError, match="row-standardized"):
        SpatialStructureGate().evaluate(np.zeros(W.shape[0]), raw_binary)


def test_insufficient_observations_rejected():
    tiny_w = np.eye(5)
    res = SpatialStructureGate().evaluate(np.arange(5, dtype=float), tiny_w)
    assert res.decision == "REJECT"
    assert "Insufficient" in res.instruction
