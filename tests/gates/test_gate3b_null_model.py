"""Gate 3b conditional null model (toroidal shift) — R-2.

The manual's own documented weakness: free permutation destroys y's own
spatial autocorrelation in every null draw, systematically understating
how often two independently-but-strongly-autocorrelated fields produce a
spuriously large bivariate statistic by chance. These tests pin the fix
(opt-in, additive) and verify it never changes existing default behavior.
"""

from __future__ import annotations

import numpy as np
import pytest

from autocarto.demo import make_grid_polygons, spatial_autoregressive
from autocarto.execution.gates.gate3b_bivariate_correlation import BivariateCorrelationGate


@pytest.fixture(scope="module")
def grid_W():
    _, W, _ = make_grid_polygons(16, 16)
    return W


# ── Backward compatibility: default behavior must be untouched ──────────────

def test_omitting_null_model_reproduces_prior_behavior_exactly(grid_W):
    """Every call that doesn't pass null_model/grid_shape must be
    byte-identical to before R-2 existed."""
    x = spatial_autoregressive(grid_W, rho=0.85, seed=1)
    y = 0.8 * x + 0.2 * spatial_autoregressive(grid_W, rho=0.85, seed=2)
    gate = BivariateCorrelationGate()

    res_implicit = gate.evaluate(x, y, grid_W, permutations=199, random_state=7)
    res_explicit_default = gate.evaluate(
        x, y, grid_W, permutations=199, random_state=7, null_model="free_permutation",
    )
    assert res_implicit.bivariate_morans_p == res_explicit_default.bivariate_morans_p
    assert res_implicit.decision == res_explicit_default.decision


def test_toroidal_shift_without_grid_shape_raises(grid_W):
    x = spatial_autoregressive(grid_W, rho=0.85, seed=1)
    y = spatial_autoregressive(grid_W, rho=0.85, seed=2)
    gate = BivariateCorrelationGate()
    with pytest.raises(ValueError, match="grid_shape"):
        gate.evaluate(x, y, grid_W, null_model="toroidal_shift")


def test_toroidal_shift_wrong_grid_shape_raises(grid_W):
    x = spatial_autoregressive(grid_W, rho=0.85, seed=1)
    y = spatial_autoregressive(grid_W, rho=0.85, seed=2)
    gate = BivariateCorrelationGate()
    with pytest.raises(ValueError, match="does not match N"):
        gate.evaluate(x, y, grid_W, null_model="toroidal_shift", grid_shape=(10, 10))


# ── The actual fix: verified against the known documented false positive ────

def test_toroidal_shift_gives_more_honest_pvalue_on_known_false_positive(grid_W):
    """The documented false-approval case (two independent SAR(0.85) fields
    on this exact grid, seed 23-derived): free permutation gives a
    misleadingly low p; toroidal shift gives a substantially higher,
    more honest one, while the statistic itself (I_xy) is unchanged."""
    x = spatial_autoregressive(grid_W, rho=0.85, seed=2301)
    y = spatial_autoregressive(grid_W, rho=0.85, seed=2302)
    gate = BivariateCorrelationGate()

    free = gate.evaluate(x, y, grid_W, permutations=999, random_state=7)
    toroidal = gate.evaluate(
        x, y, grid_W, permutations=999, random_state=7,
        null_model="toroidal_shift", grid_shape=(16, 16),
    )

    assert free.bivariate_morans_i == toroidal.bivariate_morans_i  # same statistic
    assert toroidal.bivariate_morans_p > free.bivariate_morans_p * 5  # >=5x more honest
    assert toroidal.bivariate_morans_p > 0.03  # free-perm's p=0.001 is misleadingly low


def test_toroidal_shift_still_detects_genuine_strong_coupling(grid_W):
    """The fix must not weaken real signal detection -- a genuinely
    coupled pair stays clearly significant under either null."""
    x = spatial_autoregressive(grid_W, rho=0.85, seed=101)
    y = 0.8 * x + 0.2 * spatial_autoregressive(grid_W, rho=0.85, seed=102)
    gate = BivariateCorrelationGate()

    toroidal = gate.evaluate(
        x, y, grid_W, permutations=999, random_state=7,
        null_model="toroidal_shift", grid_shape=(16, 16),
    )
    assert toroidal.bivariate_morans_p < 0.01
    assert toroidal.decision == "APPROVE"


def test_toroidal_shift_preserves_ys_own_autocorrelation_by_construction():
    """Sanity check on the mechanism itself: a toroidal shift must leave
    every pairwise relationship among y's own values unchanged (it's a
    rigid translation), unlike a free shuffle which destroys them all."""
    rng = np.random.default_rng(0)
    y = rng.standard_normal((8, 8))
    shifted = np.roll(np.roll(y, 3, axis=0), 5, axis=1)
    # The multiset of values is identical -- nothing was altered, only moved.
    assert sorted(y.ravel()) == sorted(shifted.ravel())
    # Undoing the shift recovers y exactly.
    restored = np.roll(np.roll(shifted, -3, axis=0), -5, axis=1)
    assert np.array_equal(restored, y)


def test_toroidal_shift_deterministic_across_calls(grid_W):
    x = spatial_autoregressive(grid_W, rho=0.85, seed=2301)
    y = spatial_autoregressive(grid_W, rho=0.85, seed=2302)
    gate = BivariateCorrelationGate()
    r1 = gate.evaluate(x, y, grid_W, permutations=199, random_state=7,
                       null_model="toroidal_shift", grid_shape=(16, 16))
    r2 = gate.evaluate(x, y, grid_W, permutations=199, random_state=7,
                       null_model="toroidal_shift", grid_shape=(16, 16))
    assert r1.bivariate_morans_p == r2.bivariate_morans_p
