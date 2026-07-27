"""Gate 6 (map completeness) behavioral tests — Blueprint §3.5."""

from __future__ import annotations

from autocarto.execution.gates.gate6_completeness import CompletenessGate, RenderManifest


def _complete_choropleth_manifest() -> RenderManifest:
    return RenderManifest(
        title="Tree Canopy Loss by Census Tract",
        legend_present=True,
        scale_bar_present=True,
        data_citation="NLCD 2021",
        crs_note="NAD83 / Conus Albers (EPSG:5070)",
        classification_note="Log-transform + Jenks, 5 classes",
    )


def test_complete_choropleth_manifest_passes():
    res = CompletenessGate().evaluate(_complete_choropleth_manifest(), "choropleth")
    assert res.decision == "PASS"
    assert res.diagnostics["missing"] == []


def test_missing_citation_rejected():
    manifest = _complete_choropleth_manifest()
    manifest.data_citation = None
    res = CompletenessGate().evaluate(manifest, "choropleth")
    assert res.decision == "REJECT"
    assert "citation" in res.diagnostics["missing"]
    assert res.prescription.method == "add_missing_elements"


def test_bivariate_requires_correlation_statistic():
    manifest = _complete_choropleth_manifest()
    manifest.bivariate_legend_present = True
    res = CompletenessGate().evaluate(manifest, "bivariate")
    assert res.decision == "REJECT"
    assert "correlation_statistic" in res.diagnostics["missing"]
    assert "legend" not in res.diagnostics["missing"]  # bivariate_legend_present satisfies it


def test_complete_bivariate_manifest_passes():
    manifest = _complete_choropleth_manifest()
    manifest.bivariate_legend_present = True
    manifest.correlation_statistic_shown = True
    res = CompletenessGate().evaluate(manifest, "bivariate")
    assert res.decision == "PASS"


def test_proportional_symbol_does_not_require_classification_note():
    manifest = RenderManifest(
        title="Cases by County", legend_present=True, graticule_present=True,
        data_citation="CDC PLACES", crs_note="EPSG:4326",
    )
    res = CompletenessGate().evaluate(manifest, "proportional_symbol")
    assert res.decision == "PASS"


def test_empty_manifest_lists_all_required_as_missing():
    res = CompletenessGate().evaluate(RenderManifest(), "choropleth")
    assert res.decision == "REJECT"
    assert set(res.diagnostics["missing"]) == set(res.diagnostics["required"])
