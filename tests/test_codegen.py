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

from matplotlib.colors import to_rgb

from autocarto.contracts import AuthorityViolation, MapProposal, ProvenancedValue, RenderPlan
from autocarto.orchestrator import _BIVARIATE_DEFAULT_PALETTE as BIVARIATE_PALETTE
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
    #
    # The note now lives in fig.texts (a fig.text() call in the legend
    # panel below the colorbar), not ax.texts -- moved off the map itself
    # per a later user request; see test_choropleth_legend_panel_is_below_colorbar_not_on_map.
    rendered_texts = " ".join(t.get_text() for t in fig.texts)
    assert "log_transform_then_jenks" in rendered_texts

    gate_res = CompletenessGate().evaluate(manifest, "choropleth")
    assert gate_res.decision == "PASS"


def test_choropleth_title_and_legend_are_human_readable(small_gdf):
    """A real user's finding: the title/legend read like raw Python
    identifiers ("median_household_income") and the colorbar showed bare
    floats ("250001") with no currency formatting. Checks the *rendered*
    output (drawn tick label text, not just the generated source string) --
    a naive check of the FuncFormatter callable alone would have missed a
    real bug this test caught: the formatter's "_unit" variable name
    collided with _SCALE_BAR_SNIPPET's own "_unit" (assigned later in the
    same script, to "m"/"deg"), so matplotlib's lazy draw-time formatting
    call silently saw the wrong value and always fell back to plain
    thousands-separator formatting -- no exception, no manifest mismatch,
    just wrong pixels."""
    proposal = MapProposal(map_type="choropleth", variables=["median_household_income"],
                           classification_method="jenks")
    plan = RenderPlan(
        breaks=ProvenancedValue([98000.0, 130256.0, 165000.0, 200000.0, 250001.0], "GATE_PRESCRIBED", "G2"),
        projection=ProvenancedValue(5070, "GATE_PRESCRIBED", "G4"),
        palette=ProvenancedValue("YlGn", "TEMPLATE_DEFAULT"),
        template_id=ProvenancedValue("choropleth_v1", "TEMPLATE_DEFAULT"),
    )
    code, manifest = generate(
        proposal, plan, citation="Source: ACS B19013", crs_note="EPSG:5070",
        variable_unit="USD",
    )

    ast.parse(code)
    exec_globals = {"gdf": small_gdf, "variable_column": "variable_column"}
    exec(compile(code, "<test>", "exec"), exec_globals)
    fig = exec_globals["fig"]

    assert "median_household_income" not in manifest.title
    assert "Median Household Income" in manifest.title

    fig.canvas.draw()
    colorbar_ax = next(a for a in fig.axes if a is not exec_globals["ax"])
    tick_labels = [t.get_text() for t in colorbar_ax.get_yticklabels()]
    plt.close(fig)

    assert tick_labels, "expected at least one colorbar tick label"
    assert all(lbl.startswith("$") and "," in lbl for lbl in tick_labels), tick_labels
    assert any("250,001" in lbl for lbl in tick_labels), tick_labels


def test_scale_bar_snaps_to_round_number():
    """A real user's finding: the scale bar showed an unrounded raw length
    ("14478 m") -- a distance nobody reasons in. _SCALE_BAR_SNIPPET now
    snaps to a cartographic "nice number" (1/2/5 x 10^n). Uses a
    deliberately non-round extent (raw 20%-of-width length is 2900 m) --
    a fixture whose raw length already happened to be round would pass
    even if the snapping code were deleted entirely."""
    gdf = gpd.GeoDataFrame(
        {"geometry": [box(i * 3000, 0, i * 3000 + 2500, 20000) for i in range(5)],
         "variable_column": [1.0, 5.0, 12.0, 30.0, 80.0]},
        crs="EPSG:5070",
    )
    proposal = MapProposal(map_type="choropleth", variables=["x"], classification_method="jenks")
    plan = RenderPlan(
        breaks=ProvenancedValue([0.5, 3.0, 6.0, 12.0, 21.0, 73.0], "GATE_PRESCRIBED", "G2"),
        projection=ProvenancedValue(5070, "GATE_PRESCRIBED", "G4"),
        palette=ProvenancedValue("YlOrRd", "TEMPLATE_DEFAULT"),
        template_id=ProvenancedValue("choropleth_v1", "TEMPLATE_DEFAULT"),
    )
    code, _ = generate(proposal, plan, citation="c", crs_note="EPSG:5070")

    exec_globals = {"gdf": gdf, "variable_column": "variable_column"}
    exec(compile(code, "<test>", "exec"), exec_globals)
    plt.close(exec_globals["fig"])

    raw_len = (gdf.total_bounds[2] - gdf.total_bounds[0]) * 0.2
    assert raw_len == pytest.approx(2900.0)  # deliberately not already round
    assert exec_globals["_bar_len"] == 2000.0

    # Checks the actual rendered segmented bar (tick labels + title), not
    # just the internal length variable -- a regression that snapped the
    # length correctly but mislabeled the segmented bar's ticks would slip
    # past a check of _bar_len alone.
    bar_ax = exec_globals["_bar_ax"]
    assert bar_ax.get_title() == "Scale (km)"
    assert [t.get_text() for t in bar_ax.get_xticklabels()] == ["0", "1", "2"]


def test_choropleth_legend_panel_is_below_colorbar_not_on_map(small_gdf):
    """A second round of user feedback on the same map: the classification
    note and scale bar used to be drawn directly on top of the map
    geometry (ax.text/ax.plot in map data coordinates) and the colorbar
    repeated the variable name as vertical text alongside its ticks.
    Checks the actual geometry of what got drawn, not just presence:
    nothing map-related left in ax.texts, the legend panel's vertical
    position sits below the colorbar's own rendered bbox, and the colorbar
    has no ylabel."""
    proposal = MapProposal(map_type="choropleth", variables=["tree_canopy_loss"],
                           classification_method="jenks")
    plan = RenderPlan(
        breaks=ProvenancedValue([0.5, 3.0, 6.0, 12.0, 21.0, 73.0], "GATE_PRESCRIBED", "G2"),
        projection=ProvenancedValue(5070, "GATE_PRESCRIBED", "G4"),
        palette=ProvenancedValue("YlOrRd", "TEMPLATE_DEFAULT"),
        template_id=ProvenancedValue("choropleth_v1", "TEMPLATE_DEFAULT"),
    )
    code, _manifest = generate(proposal, plan, citation="c", crs_note="EPSG:5070")

    exec_globals = {"gdf": small_gdf, "variable_column": "variable_column"}
    exec(compile(code, "<test>", "exec"), exec_globals)
    fig = exec_globals["fig"]
    ax = exec_globals["ax"]

    assert len(ax.texts) == 0, "classification note must not be drawn on the map axes anymore"

    cb = exec_globals["_cb"]
    assert cb.ax.get_ylabel() == "", "colorbar must not repeat the variable name as vertical text"

    cb_box = cb.ax.get_position()
    bar_ax = exec_globals["_bar_ax"]
    bar_box = bar_ax.get_position()
    assert bar_box.y1 <= cb_box.y0, "scale bar panel must sit below the colorbar, not beside/over it"

    note_text = next(t for t in fig.texts if "jenks" in t.get_text())
    note_y = note_text.get_position()[1]
    assert note_y <= cb_box.y0, "classification note must sit below the colorbar, not over the map"
    assert note_y >= bar_box.y1, "classification note must be above the scale bar, per the requested stacking order"

    plt.close(fig)


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
    exec_globals = {
        "gdf": small_gdf,
        "bivariate_colors": ["#e8e8e8"] * 5,
        "bivariate_palette": list(BIVARIATE_PALETTE),
    }
    exec(compile(code, "<test>", "exec"), exec_globals)
    fig = exec_globals["fig"]
    assert isinstance(fig, plt.Figure)

    assert manifest.bivariate_legend_present is True
    assert manifest.correlation_statistic_shown is True
    assert manifest.classification_note is not None

    # Same real-execution check as the choropleth test above: bivariate_v1
    # claimed "classification_note" as guaranteed (TEMPLATES dict) but had
    # no text-drawing call for it at all before this fix -- only
    # correlation_note was ever actually rendered. The note now lives in the
    # side panel (fig.texts), not over the map.
    rendered_texts = " ".join(t.get_text() for t in fig.texts)
    assert "tertile" in rendered_texts.lower()

    gate_res = CompletenessGate().evaluate(manifest, "bivariate")
    assert gate_res.decision == "PASS"
    plt.close(fig)


def test_bivariate_legend_is_actually_drawn_and_matches_the_map(small_gdf):
    """Gate 6 reported bivariate_legend present with missing:[] on a map that
    had no key anywhere on it. bivariate_v1 declared "bivariate_legend" in
    its guaranteed_elements while the template contained zero legend-drawing
    code, and Gate 6 trusts the manifest by design -- the same defect class
    as the earlier classification_note bug, on the one element a bivariate
    map is unreadable without.

    Checks the rendered artifact, not the manifest, and checks that the key's
    colours are the ones the polygons were actually filled from: a legend
    that exists but disagrees with the map is worse than none."""
    proposal = MapProposal(map_type="bivariate", variables=["median_household_income", "asthma_prevalence"])
    plan = RenderPlan(
        breaks=ProvenancedValue(None, "TEMPLATE_DEFAULT"),
        projection=ProvenancedValue(5070, "GATE_PRESCRIBED", "G4"),
        palette=ProvenancedValue(list(BIVARIATE_PALETTE), "TEMPLATE_DEFAULT"),
        template_id=ProvenancedValue("bivariate_v1", "TEMPLATE_DEFAULT"),
    )
    code, _manifest = generate(
        proposal, plan, citation="c", crs_note="EPSG:5070",
        correlation_note="Bivariate Moran's I = -0.555   ·   Spearman ρ = -0.776   ·   Gate 3b: PASS",
    )

    exec_globals = {
        "gdf": small_gdf,
        "bivariate_colors": ["#e8e8e8"] * 5,
        "bivariate_palette": list(BIVARIATE_PALETTE),
    }
    exec(compile(code, "<test>", "exec"), exec_globals)
    fig = exec_globals["fig"]
    ax = exec_globals["ax"]

    # A 3x3 key was actually rasterised somewhere in the figure.
    images = [im for a in fig.axes for im in a.images]
    assert images, "no bivariate key was drawn -- Gate 6 would still report it present"
    key = images[0]
    assert key.get_array().shape[:2] == (3, 3)

    # Every one of the 9 palette colours appears in the key, and the corner
    # cells are the ones the tertile assignment actually produces:
    # grid[x_class][y_class], flipped so y increases upward.
    grid = [list(BIVARIATE_PALETTE)[i * 3:i * 3 + 3] for i in range(3)]
    arr = key.get_array()
    assert tuple(np.round(arr[2][0], 5)) == tuple(np.round(to_rgb(grid[0][0]), 5))  # bottom-left: low/low
    assert tuple(np.round(arr[2][2], 5)) == tuple(np.round(to_rgb(grid[2][0]), 5))  # bottom-right: high x, low y
    assert tuple(np.round(arr[0][0], 5)) == tuple(np.round(to_rgb(grid[0][2]), 5))  # top-left: low x, high y

    # Axis labels name the variables in the order the colour lookup uses.
    kax = key.axes
    assert "Median Household Income" in kax.get_xlabel()
    assert "Asthma Prevalence" in kax.get_ylabel()

    # Nothing is painted over the geometry any more.
    assert len(ax.texts) == 0, "notes must sit in the side panel, not over the map"
    plt.close(fig)


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
