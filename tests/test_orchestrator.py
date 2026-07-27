"""Orchestrator end-to-end tests — Blueprint §4 acceptance criteria.

These exercise the full Propose-Verify-Execute loop against real spatially-
correlated (SAR) data on a real Queen-contiguity weight matrix, entirely
offline (MockLLM, no network) — the P2 acceptance bar from Manual §11:
"autocarto run '...' --llm mock produces a validated map + trace offline."
"""

from __future__ import annotations

import json

import geopandas as gpd
import libpysal
import matplotlib
matplotlib.use("Agg")
import numpy as np
import pytest
from scipy.linalg import solve
from shapely.geometry import box

from autocarto.contracts import MapProposal, SemanticContext
from autocarto.orchestrator import Dataset, Orchestrator
from autocarto.semantic.llm_client import LLMCallRecord, LLMClient, MockLLM


def _sar_draw(W: np.ndarray, rho: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    A = np.eye(W.shape[0]) - rho * W
    eps = rng.standard_normal(W.shape[0])
    return solve(A, eps)


@pytest.fixture(scope="module")
def grid_dataset() -> Dataset:
    n_side = 8
    gdf = gpd.GeoDataFrame(
        {"geometry": [box(i, j, i + 1, j + 1) for i in range(n_side) for j in range(n_side)]},
        crs="EPSG:5070",
    )
    w = libpysal.weights.lat2W(n_side, n_side)
    w.transform = "r"
    W = w.full()[0]
    z = _sar_draw(W, rho=0.75, seed=42)
    tree_canopy = np.clip(np.exp(z * 0.9) * 7.5, 0.5, 95.0)  # heavy right skew, like the real Atlanta case
    return Dataset(
        id="synthetic-grid", gdf=gdf,
        variables={"tree_canopy_loss": tree_canopy},
        variable_roles={"tree_canopy_loss": "density"},
        weights=W, citation="Source: synthetic SAR (test fixture)",
    )


@pytest.fixture(scope="module")
def bivariate_dataset() -> Dataset:
    n_side = 8
    gdf = gpd.GeoDataFrame(
        {"geometry": [box(i, j, i + 1, j + 1) for i in range(n_side) for j in range(n_side)]},
        crs="EPSG:5070",
    )
    w = libpysal.weights.lat2W(n_side, n_side)
    w.transform = "r"
    W = w.full()[0]
    z_common = _sar_draw(W, rho=0.75, seed=1)
    x = 0.8 * z_common + 0.2 * _sar_draw(W, rho=0.3, seed=2)
    y = 0.75 * z_common + 0.25 * _sar_draw(W, rho=0.3, seed=3)
    return Dataset(
        id="bivariate-grid", gdf=gdf,
        variables={"canopy": x, "asthma": y},
        variable_roles={"canopy": "density", "asthma": "rate"},
        weights=W, citation="Source: synthetic SAR bivariate (test fixture)",
    )


# ── Full convergence: REJECT -> mandate -> transcribe -> PASS -> render ──────

def test_choropleth_converges_via_mandate_and_renders(grid_dataset):
    orch = Orchestrator(llm=MockLLM(), max_iter=3, seed=0)
    result = orch.run("Map tree canopy loss", grid_dataset)

    assert result.success is True
    assert result.human_review is False
    # First proposal is naive (no breaks) and must be rejected; the
    # architecture's whole thesis is that this converges quickly, not on
    # the first try.
    assert len(result.trace["iterations"]) >= 2
    assert result.trace["iterations"][0]["gate_suite"]["decision"] == "REJECT"
    assert result.trace["iterations"][-1]["gate_suite"]["decision"] != "REJECT"
    assert result.iterations <= 3

    assert result.manifest is not None
    assert result.manifest.title is not None
    assert result.manifest.legend_present is True
    assert result.figure is not None
    assert len(result.figure.axes) >= 1


def test_render_plan_values_are_never_free_llm_on_success(grid_dataset):
    """Spot-check invariant #2 held for a real successful run: nothing in
    the trace's final gate suite is unvalidated."""
    orch = Orchestrator(llm=MockLLM(), max_iter=3, seed=0)
    result = orch.run("Map tree canopy loss", grid_dataset)
    assert result.success is True
    final_suite = result.trace["iterations"][-1]["gate_suite"]
    assert final_suite["decision"] != "REJECT"
    assert final_suite["rejection_count"] == 0


def test_trace_is_valid_json(grid_dataset):
    orch = Orchestrator(llm=MockLLM(), max_iter=3, seed=0)
    result = orch.run("Map tree canopy loss", grid_dataset)
    parsed = json.loads(result.trace_json())
    assert parsed["prompt"] == "Map tree canopy loss"
    assert parsed["dataset_id"] == "synthetic-grid"


def test_bivariate_map_with_strong_correlation_passes(bivariate_dataset):
    orch = Orchestrator(llm=MockLLM(), max_iter=3, seed=0)
    result = orch.run("Map canopy loss vs asthma rate", bivariate_dataset)

    assert result.success is True
    assert result.manifest.bivariate_legend_present is True
    assert result.manifest.correlation_statistic_shown is True
    assert result.figure is not None


# ── Human-review escape hatch (Blueprint §4: "Mandate --> HumanReview: iter > 3") ──

def test_zero_max_iter_on_skewed_data_goes_to_human_review(grid_dataset):
    """With no mandate iterations allowed, the naive first proposal (no
    breaks) fails Gate 2 on skewed data and there is no second chance."""
    orch = Orchestrator(llm=MockLLM(), max_iter=0, seed=0)
    result = orch.run("Map tree canopy loss", grid_dataset)

    assert result.success is False
    assert result.human_review is True
    assert result.insufficiency_report is not None
    assert "human review" in result.insufficiency_report.lower()


# ── Authority boundary: the LLM never receives raw data ──────────────────────

class _SpyLLM(LLMClient):
    """Records every SemanticContext it is given, for post-hoc inspection."""
    provider = "spy"
    model = "spy"
    version = "1.0"

    def __init__(self):
        self.seen_contexts: list = []
        self._inner = MockLLM()

    def propose(self, context: SemanticContext, prompt: str):
        self.seen_contexts.append(context)
        return self._inner.propose(context, prompt)


def test_llm_never_receives_raw_data_across_full_run(grid_dataset):
    spy = _SpyLLM()
    orch = Orchestrator(llm=spy, max_iter=3, seed=0)
    result = orch.run("Map tree canopy loss", grid_dataset)

    assert result.success is True
    assert len(spy.seen_contexts) >= 2  # at least the naive pass + the mandated re-propose

    for ctx in spy.seen_contexts:
        # SemanticContext's own constructor already enforces this (it would
        # have raised AuthorityViolation), but assert it positively too:
        # every schema is a name/dtype/role triple, never an array.
        for schema in ctx.dataset_schemas:
            assert isinstance(schema.name, str)
            assert isinstance(schema.dtype, str)
        # The AOI carries a bbox tuple and a feature count, not geometry.
        assert isinstance(ctx.aoi.bbox_4326, tuple)
        assert isinstance(ctx.aoi.feature_count, int)
