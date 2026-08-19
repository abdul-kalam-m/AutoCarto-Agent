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
import numpy as np
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


def test_population_density_is_area_normalised_and_equal_area_gated():
    """population_density (ACS B01003 / tract area) is the only variable in
    this dataset for which Gate 1's equal-area requirement is load-bearing
    rather than conservative: polygon area is literally its denominator, so
    deriving it under a geographic CRS would bake in the exact error Gate 1
    exists to catch. Asserts the role is tagged so the gate actually fires,
    and that the density was computed in an equal-area projection."""
    ds = load_real_atlanta_dataset(variables=["population_density"])
    assert ds.variable_roles["population_density"] == "density"
    assert ds.gdf.crs.to_epsg() == 5070  # CONUS Albers, equal-area

    d = ds.variables["population_density"]
    # Sanity on magnitude: these are people per km2 for an urban county. A
    # degrees-squared denominator (the Gate 1 error) would be off by orders
    # of magnitude, so the upper end is the discriminating check.
    #
    # The minimum is legitimately 0.0 here and that is not a missing value:
    # requesting population_density alone drops only tracts missing THAT
    # variable, and population has no Census sentinels, so the two
    # zero-population tracts (airport land) survive with a true density of
    # zero. They disappear from the default dataset only because income and
    # asthma are absent for them.
    assert d.min() >= 0.0
    assert 10_000 < d.max() < 100_000
    assert 500 < float(np.median(d)) < 5_000


def test_population_density_prompt_resolves_to_density_not_a_substitute():
    """The bug this variable was added around: 'Map of Population Density'
    previously rendered a Median Household Income choropleth, because the
    name was absent from the schema and the intent validator substituted
    the first available variable. It must now resolve to the real thing."""
    ds = load_real_atlanta_dataset()
    assert "population_density" in ds.variables, (
        "population_density must be in the DEFAULT variable set -- Tier 1 "
        "resolves prompts only against the schema it is handed, so a "
        "variable missing from the default is unmappable from a prompt."
    )
    names = [s.name for s in ds.to_field_schemas()]
    assert names.index("median_household_income") < names.index("population_density"), (
        "income/asthma must stay first: bivariate proposals consume "
        "variables[0] and variables[1], so reordering would silently change "
        "the default bivariate pairing."
    )


def test_real_data_gate2_naive_proposal_rejected_then_converges():
    """Even real, 'well_behaved' data shouldn't pass a naive proposal with
    no breaks -- Gate 2 still has something to check on the first pass."""
    ds = load_real_atlanta_dataset(variables=["median_household_income"])
    orch = Orchestrator(llm=MockLLM(), max_iter=3, seed=0)
    result = orch.run("Map median household income", ds)

    assert result.trace["iterations"][0]["gate_suite"]["decision"] == "REJECT"
    assert result.success is True
    assert result.iterations >= 1
