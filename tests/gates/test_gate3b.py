"""Gate 3b behavioral contracts (decision matrix, W contract, edge cases)."""

from __future__ import annotations

import numpy as np
import pytest

from autocarto.demo import make_grid_polygons, spatial_autoregressive
from autocarto.execution.gates.gate3b_bivariate_correlation import (
    BivariateCorrelationGate,
)


@pytest.fixture(scope="module")
def grid_W():
    _, W, _ = make_grid_polygons(16, 16)
    return W


def _run(gate, x, y, W, **kw):
    kw.setdefault("standardized", False)
    kw.setdefault("permutations", 199)
    kw.setdefault("random_state", 7)
    return gate.evaluate(x, y, W, **kw)


# ── The three demo scenarios (decisions pinned; exact floats in golden test) ──

def test_strong_coupling_approved(grid_W):
    x = spatial_autoregressive(grid_W, rho=0.85, seed=1)
    y = 0.8 * x + 0.2 * spatial_autoregressive(grid_W, rho=0.85, seed=2)
    res = _run(BivariateCorrelationGate(), x, y, grid_W)
    assert res.decision == "APPROVE"
    assert res.bivariate_morans_p <= 0.05
    assert abs(res.bivariate_morans_i) > BivariateCorrelationGate.APPROVE_I_THRESHOLD


def test_weak_coupling_warned(grid_W):
    x = spatial_autoregressive(grid_W, rho=0.6, seed=3)
    y = 0.2 * x + spatial_autoregressive(grid_W, rho=0.4, seed=4)
    res = _run(BivariateCorrelationGate(), x, y, grid_W)
    assert res.decision == "WARN"
    assert "annotation" in res.instruction.lower()


def test_independent_fields_rejected_with_mandated_alternative(grid_W):
    x = spatial_autoregressive(grid_W, rho=0.85, seed=5)
    y = spatial_autoregressive(grid_W, rho=0.85, seed=6)
    res = _run(BivariateCorrelationGate(), x, y, grid_W)
    assert res.decision == "REJECT"
    assert res.bivariate_morans_p > 0.05
    assert "side-by-side" in res.instruction.lower()


# ── Contract enforcement (reviewer patch R2-3) ────────────────────────────────

def test_raw_binary_weights_matrix_raises(grid_W):
    x = spatial_autoregressive(grid_W, rho=0.85, seed=1)
    y = spatial_autoregressive(grid_W, rho=0.85, seed=2)
    W_raw = (grid_W > 0).astype(float)          # binary, row sums 3..8
    with pytest.raises(ValueError, match="row-standardized"):
        _run(BivariateCorrelationGate(), x, y, W_raw)


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_constant_variable_cleanly_rejected(grid_W):
    x = spatial_autoregressive(grid_W, rho=0.85, seed=1)
    y = np.full_like(x, 3.14)
    res = _run(BivariateCorrelationGate(), x, y, grid_W)
    assert res.decision == "REJECT"
    assert "constant" in res.instruction.lower()


def test_insufficient_observations_rejected(grid_W):
    gate = BivariateCorrelationGate()
    x = np.arange(10, dtype=float)
    y = np.arange(10, dtype=float)
    res = _run(gate, x, y, np.full((10, 10), 0.1))
    assert res.decision == "REJECT"


def test_nan_masking_keeps_weights_aligned(grid_W):
    x = spatial_autoregressive(grid_W, rho=0.85, seed=1)
    y = 0.8 * x + 0.2 * spatial_autoregressive(grid_W, rho=0.85, seed=2)
    x_nan = x.copy()
    x_nan[[0, 17, 42]] = np.nan
    res = _run(BivariateCorrelationGate(), x_nan, y, grid_W)
    # Must still run and still approve; masking drops rows/cols consistently.
    assert res.decision == "APPROVE"


def test_permutation_pvalue_is_seed_deterministic(grid_W):
    x = spatial_autoregressive(grid_W, rho=0.85, seed=1)
    y = 0.8 * x + 0.2 * spatial_autoregressive(grid_W, rho=0.85, seed=2)
    r1 = _run(BivariateCorrelationGate(), x, y, grid_W, random_state=7)
    r2 = _run(BivariateCorrelationGate(), x, y, grid_W, random_state=7)
    assert r1.bivariate_morans_p == r2.bivariate_morans_p
    assert r1.bivariate_morans_i == r2.bivariate_morans_i


def test_json_safety_of_result(grid_W):
    import json
    x = spatial_autoregressive(grid_W, rho=0.85, seed=1)
    y = 0.8 * x + 0.2 * spatial_autoregressive(grid_W, rho=0.85, seed=2)
    res = _run(BivariateCorrelationGate(), x, y, grid_W)
    json.dumps(res.to_dict())  # must not raise (reviewer patch G3b-3)
