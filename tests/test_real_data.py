"""Real-data orchestrator tests — Blueprint §6.3 P4-T1 utility case study.

Unlike test_orchestrator.py's synthetic SAR fixtures (known ground truth,
the *validity* demonstration), these run the full Propose-Verify-Execute
loop against real ACS income + real CDC PLACES asthma data on real TIGER
geometry — the *utility* demonstration: does the system produce something
sensible on data nobody engineered to have a particular structure.

Skipped if the real-data snapshots or the geo extra aren't present, same
guard pattern as the other snapshot-dependent tests in this suite.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import pytest

geopandas = pytest.importorskip("geopandas")
libpysal = pytest.importorskip("libpysal")

from autocarto.orchestrator import Orchestrator
from autocarto.real_data import ACS_SNAPSHOT, CDC_SNAPSHOT, TIGER_SNAPSHOT, load_real_atlanta_dataset
from autocarto.semantic.llm_client import MockLLM

pytestmark = pytest.mark.skipif(
    not (TIGER_SNAPSHOT.exists() and ACS_SNAPSHOT.exists() and CDC_SNAPSHOT.exists()),
    reason="real-data snapshots not present (see data/MANIFEST.md)",
)


def test_real_dataset_drops_only_nonresidential_tracts():
    ds = load_real_atlanta_dataset()
    # 530 TIGER tracts minus the non-residential/missing-data tracts.
    assert 515 <= len(ds.gdf) <= 525
    assert ds.weights.shape == (len(ds.gdf), len(ds.gdf))


def test_real_bivariate_income_vs_asthma_converges_and_renders():
    ds = load_real_atlanta_dataset()
    orch = Orchestrator(llm=MockLLM(), max_iter=3, seed=0)
    result = orch.run("Map median household income vs asthma prevalence in Atlanta", ds)

    assert result.success is True
    assert result.figure is not None
    assert result.trace["gate6"]["decision"] == "PASS"

    g3b = next(
        g for g in result.trace["iterations"][-1]["gate_suite"]["gates"] if g["gate"] == "G3b"
    )
    # Real income/asthma health disparity: not asserting the exact value
    # (that would be a synthetic-style golden number for real-world data,
    # which can legitimately drift on re-snapshot) -- asserting the
    # well-documented *direction* and that it's strong enough to approve.
    assert g3b["diagnostics"]["bivariate_morans_i"] < 0  # income up, asthma down
    assert g3b["decision"] == "PASS"  # APPROVE, normalized to PASS


def test_real_univariate_income_shows_real_spatial_clustering():
    ds = load_real_atlanta_dataset(variables=["median_household_income"])
    orch = Orchestrator(llm=MockLLM(), max_iter=3, seed=0)
    result = orch.run("Map median household income in Atlanta", ds)

    assert result.success is True
    g3a = next(
        g for g in result.trace["iterations"][0]["gate_suite"]["gates"] if g["gate"] == "G3a"
    )
    # Income is well known to cluster spatially (wealthy/poor neighborhoods
    # aren't randomly scattered) -- real data should show this, not just
    # pass because a synthetic generator was told to produce clustering.
    assert g3a["diagnostics"]["morans_i"] > 0.3
    assert g3a["decision"] == "PASS"

    # A real user's finding: an income-only map's citation footer claimed
    # "Asthma: CDC PLACES 2023, measure CASTHMA" -- data this specific map
    # never touched -- because Dataset.citation was one flat string
    # describing the whole dataset, not the one map actually rendered.
    # Fixed via Dataset.citation_by_variable + Orchestrator._resolve_citation;
    # this asserts the fix on the real scenario that exposed the bug, not a
    # synthetic reproduction of it.
    assert "CASTHMA" not in result.code
    assert "Asthma" not in result.code
    assert "Census ACS" in result.code  # the citation for the variable actually used


def test_real_bivariate_citation_mentions_both_sources():
    """The other half of the same fix: a map that DOES use both variables
    should cite both -- _resolve_citation must not over-correct into
    dropping a fragment that's actually relevant."""
    ds = load_real_atlanta_dataset()
    orch = Orchestrator(llm=MockLLM(), max_iter=3, seed=0)
    result = orch.run("Map median household income vs asthma prevalence in Atlanta", ds)

    assert result.success is True
    assert "Census ACS" in result.code
    assert "CDC PLACES" in result.code


def test_real_data_gate2_naive_proposal_rejected_then_converges():
    """Even real, 'well_behaved' data shouldn't pass a naive proposal with
    no breaks -- Gate 2 still has something to check on the first pass."""
    ds = load_real_atlanta_dataset(variables=["median_household_income"])
    orch = Orchestrator(llm=MockLLM(), max_iter=3, seed=0)
    result = orch.run("Map median household income", ds)

    assert result.trace["iterations"][0]["gate_suite"]["decision"] == "REJECT"
    assert result.success is True
    assert result.iterations >= 1
