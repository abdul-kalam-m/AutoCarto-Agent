"""Regression tests for the case-study figures' data claims.

These assert the numbers printed ON the figures (class collapse, prescribed
method, tract count) so a refactor cannot silently invalidate the poster
visuals. Rendering itself is not exercised here — only the computed inputs.

Skipped when the [geo] extra (geopandas/libpysal) or the pinned snapshot is
unavailable, so the core CI job stays dependency-light.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

pytest.importorskip("geopandas")
pytest.importorskip("libpysal")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = os.path.join(REPO_ROOT, "data", "atlanta_tracts_fulton_dekalb.geojson")
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

pytestmark = pytest.mark.skipif(
    not os.path.exists(SNAPSHOT),
    reason="Atlanta TIGER snapshot not present (run scripts/snapshot_tiger.py)",
)


@pytest.fixture(scope="module")
def case():
    from _atlanta_case import build_atlanta_case
    return build_atlanta_case(live=False)


def test_snapshot_has_530_tracts(case):
    assert case.n == 530


def test_gate2_prescribes_log_jenks_for_canopy(case):
    from autocarto.execution.gates.gate2_classification import ClassificationDiagnosticEngine
    res = ClassificationDiagnosticEngine(random_state=0).evaluate(
        case.tree_canopy, proposed_method="jenks"
    )
    assert res.diagnosis == "heavy_right_skew"
    assert res.prescribed_method == "log_transform_then_jenks"


def test_equal_interval_collapses_majority_into_one_class(case):
    """The figure's headline claim: naive equal-interval hides the pattern."""
    v = case.tree_canopy
    lo, hi = float(v.min()), float(v.max())
    breaks = [lo + (hi - lo) * k / 5 for k in range(6)]
    cls = np.digitize(v, breaks[1:-1])
    counts = [int((cls == k).sum()) for k in range(5)]
    assert max(counts) / case.n > 0.70          # ~78% land in one class
    assert counts[-1] < 10                       # top class nearly empty


def test_prescribed_classes_are_balanced(case):
    from autocarto.execution.gates.gate2_classification import (
        ClassificationDiagnosticEngine, _dedupe_breaks,
    )
    v = case.tree_canopy
    res = ClassificationDiagnosticEngine(random_state=0).evaluate(v, proposed_method="jenks")
    breaks = _dedupe_breaks([float(b) for b in res.prescribed_breaks])
    cls = np.digitize(v, breaks[1:-1])
    counts = [int((cls == k).sum()) for k in range(len(breaks) - 1)]
    # No single prescribed class dominates the way equal-interval's does.
    assert max(counts) / case.n < 0.40
