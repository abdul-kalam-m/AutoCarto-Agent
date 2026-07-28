"""Constrained code generator tests — Blueprint §5.

Each template is verified three ways: (1) the generated source parses as
valid Python, (2) executing it against real GeoDataFrame data produces an
actual matplotlib Figure (not just syntactically plausible text), and
(3) the manifest it returns satisfies Gate 6 for that map type.
"""

from __future__ import annotations

import ast

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest
from shapely.geometry import box

from autocarto.contracts import AuthorityViolation, MapProposal, ProvenancedValue, RenderPlan
from autocarto.execution.gates.gate6_completeness import CompletenessGate
from autocarto.semantic.codegen import generate


@pytest.fixture
def small_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"geometry": [box(i, 0, i + 1, 1) for i in range(5)],
         "variable_column": [1.0, 5.0, 12.0, 30.0, 80.0]},
        crs="EPSG:4326",
    )


def test_choropleth_template_executes_and_produces_figure(small_gdf):
    proposal = MapProposal(map_type="choropleth", variables=["tree_canopy_loss"],
                           classification_method="log_transform_then_jenks")
    plan = RenderPlan(
        breaks=ProvenancedValue([0.5, 3.0, 6.0, 12.0, 21.0, 73.0], "GATE_PRESCRIBED", "G2"),
        projection=ProvenancedValue(5070, "GATE_PRESCRIBED", "G4"),
        palette=ProvenancedValue("YlOrRd", "TEMPLATE_DEFAULT"),
        template_id=ProvenancedValue("choropleth_v1", "TEMPLATE_DEFAULT"),
    )
    code, manifest = generate(proposal, plan, citation="Source: NLCD 2021", crs_note="EPSG:5070")

    ast.parse(code)  # syntax check
    exec_globals = {"gdf": small_gdf, "variable_column": "variable_column"}
    exec(compile(code, "<test>", "exec"), exec_globals)
    fig = exec_globals["fig"]
    assert isinstance(fig, plt.Figure)
    plt.close(fig)

    assert manifest.title is not None
    assert manifest.legend_present is True
    assert manifest.data_citation == "Source: NLCD 2021"
    assert "log_transform_then_jenks" in manifest.classification_note

    # Not just "does the manifest claim this" -- does the generated code
    # actually draw it. A prior version of generate() populated
    # manifest.classification_note unconditionally, regardless of whether
    # choropleth_v1's template had any text-drawing call for it at all, so
    # this exact assertion (checking the manifest only) would have passed
    # even while the figure itself showed nothing -- a real user caught the
    # gap by comparing a rendered map against its trace.
    rendered_texts = " ".join(t.get_text() for t in fig.axes[0].texts)
    assert "log_transform_then_jenks" in rendered_texts

    gate_res = CompletenessGate().evaluate(manifest, "choropleth")
    assert gate_res.decision == "PASS"


def test_bivariate_template_executes_and_satisfies_gate6(small_gdf):
    proposal = MapProposal(map_type="bivariate", variables=["tree_canopy_loss", "asthma_rate"])
    plan = RenderPlan(
        breaks=ProvenancedValue(None, "TEMPLATE_DEFAULT"),
        projection=ProvenancedValue(5070, "GATE_PRESCRIBED", "G4"),
        palette=ProvenancedValue(
            ["#e8e8e8", "#ace4e4", "#5ac8c8", "#dfb0d6", "#a5add3",
             "#5698b9", "#be64ac", "#8c62aa", "#3b4994"],
            "TEMPLATE_DEFAULT",
        ),
        template_id=ProvenancedValue("bivariate_v1", "TEMPLATE_DEFAULT"),
    )
    code, manifest = generate(
        proposal, plan, citation="Source: TIGER + SAR", crs_note="EPSG:5070",
        correlation_note="I_xy=+0.326, rho=+0.947, APPROVE",
    )

    ast.parse(code)
    exec_globals = {"gdf": small_gdf, "bivariate_colors": ["#e8e8e8"] * 5}
    exec(compile(code, "<test>", "exec"), exec_globals)
    fig = exec_globals["fig"]
    assert isinstance(fig, plt.Figure)
    plt.close(fig)

    assert manifest.bivariate_legend_present is True
    assert manifest.correlation_statistic_shown is True
    assert manifest.classification_note is not None

    # Same real-execution check as the choropleth test above: bivariate_v1
    # claimed "classification_note" as guaranteed (TEMPLATES dict) but had
    # no text-drawing call for it at all before this fix -- only
    # correlation_note was ever actually rendered.
    rendered_texts = " ".join(t.get_text() for t in fig.axes[0].texts)
    assert "tertile" in rendered_texts.lower()

    gate_res = CompletenessGate().evaluate(manifest, "bivariate")
    assert gate_res.decision == "PASS"


def test_proportional_symbol_template_executes(small_gdf):
    proposal = MapProposal(map_type="proportional_symbol", variables=["case_count"])
    plan = RenderPlan(
        breaks=ProvenancedValue(None, "TEMPLATE_DEFAULT"),
        projection=ProvenancedValue(4326, "TEMPLATE_DEFAULT"),
        palette=ProvenancedValue("#2166ac", "TEMPLATE_DEFAULT"),
        template_id=ProvenancedValue("proportional_symbol_v1", "TEMPLATE_DEFAULT"),
    )
    code, manifest = generate(proposal, plan, citation="Source: CDC PLACES", crs_note="EPSG:4326")

    ast.parse(code)
    exec_globals = {"gdf": small_gdf, "values": np.array([1.0, 5.0, 12.0, 30.0, 80.0])}
    exec(compile(code, "<test>", "exec"), exec_globals)
    fig = exec_globals["fig"]
    assert isinstance(fig, plt.Figure)
    plt.close(fig)

    gate_res = CompletenessGate().evaluate(manifest, "proportional_symbol")
    assert gate_res.decision == "PASS"


def test_free_llm_provenance_blocks_codegen_entirely():
    proposal = MapProposal(map_type="choropleth", variables=["x"])
    bad_plan = RenderPlan(
        breaks=ProvenancedValue([1, 2, 3], "FREE_LLM"),
        projection=ProvenancedValue(5070, "GATE_PRESCRIBED", "G4"),
        palette=ProvenancedValue("YlOrRd", "TEMPLATE_DEFAULT"),
        template_id=ProvenancedValue("choropleth_v1", "TEMPLATE_DEFAULT"),
    )
    with pytest.raises(AuthorityViolation):
        generate(proposal, bad_plan, citation="x")


def test_unknown_template_id_rejected():
    proposal = MapProposal(map_type="choropleth", variables=["x"])
    plan = RenderPlan(
        breaks=ProvenancedValue([1, 2], "TEMPLATE_DEFAULT"),
        projection=ProvenancedValue(4326, "TEMPLATE_DEFAULT"),
        palette=ProvenancedValue("x", "TEMPLATE_DEFAULT"),
        template_id=ProvenancedValue("nonexistent_template", "TEMPLATE_DEFAULT"),
    )
    with pytest.raises(ValueError, match="Unknown template_id"):
        generate(proposal, plan, citation="x")
