"""Gate 6: Map Completeness.

The last gate in execution order (contracts.GATE_ORDER) — it audits the
renderer's own manifest of what elements actually made it onto the figure,
against a required-element checklist that varies by map type (config.py /
Blueprint §3.5). A map can pass every statistical gate and still fail its
job as a map if it has no title, no citation, or no legend explaining what
the colors mean.

This is a declarative checklist, not a pixel inspection: Gate 6 trusts the
`RenderManifest` the renderer emits. Making that manifest emission
unavoidable is a renderer/codegen responsibility (Manual §8.2 / Blueprint
§5 constrained code generator) — Gate 6 just enforces the contract once
the manifest exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from autocarto.config import THRESHOLDS
from autocarto.contracts import GateResult, Prescription

MapType = Literal["choropleth", "bivariate", "proportional_symbol"]

_HOW_TO_SUPPLY = {
    "title": "Set a descriptive title via ax.set_title(...) stating variable and geography.",
    "legend": "Add a legend for the classification breaks (e.g. legend_kwds in gdf.plot).",
    "bivariate_legend": "Add the 3x3 bivariate legend swatch (see the bivariate render template).",
    "scale_or_graticule": "Add a scale bar (matplotlib-scalebar) or a lat/lon graticule.",
    "citation": "Add a data source citation as a figure caption or footer text.",
    "crs_note": "Note the map's CRS/projection in a caption (e.g. 'NAD83 / Conus Albers').",
    "classification_note": "State the classification method and class count in the legend/caption.",
    "correlation_statistic": (
        "Display the Gate 3b bivariate Moran's I / Spearman rho that justified "
        "this bivariate encoding — the map should be self-documenting about why."
    ),
}


@dataclass
class RenderManifest:
    """What the renderer actually produced — the artifact Gate 6 audits.

    Every field defaults to "absent"; the renderer must explicitly set
    each one to True/non-empty as it adds the corresponding element.
    """
    title: Optional[str] = None
    legend_present: bool = False
    bivariate_legend_present: bool = False
    scale_bar_present: bool = False
    graticule_present: bool = False
    data_citation: Optional[str] = None
    crs_note: Optional[str] = None
    classification_note: Optional[str] = None
    correlation_statistic_shown: bool = False

    def has(self, element: str) -> bool:
        return {
            "title": bool(self.title),
            "legend": self.legend_present,
            "bivariate_legend": self.bivariate_legend_present,
            "scale_or_graticule": self.scale_bar_present or self.graticule_present,
            "citation": bool(self.data_citation),
            "crs_note": bool(self.crs_note),
            "classification_note": bool(self.classification_note),
            "correlation_statistic": self.correlation_statistic_shown,
        }.get(element, False)


class CompletenessGate:
    """Gate 6: rejects renders missing required cartographic elements."""

    _REQUIRED_BY_MAP_TYPE = {
        "choropleth": THRESHOLDS.gate6.required_elements_choropleth,
        "bivariate": THRESHOLDS.gate6.required_elements_bivariate,
        "proportional_symbol": THRESHOLDS.gate6.required_elements_proportional_symbol,
    }

    def evaluate(self, manifest: RenderManifest, map_type: MapType) -> GateResult:
        required = self._REQUIRED_BY_MAP_TYPE[map_type]
        missing = [el for el in required if not manifest.has(el)]
        diagnostics: Dict[str, Any] = {
            "map_type": map_type,
            "required": list(required),
            "missing": missing,
        }

        if missing:
            return GateResult(
                gate_id="G6",
                decision="REJECT",
                diagnostics=diagnostics,
                instruction=f"Map is missing required elements: {missing}",
                prescription=Prescription(
                    method="add_missing_elements",
                    instruction=" ".join(_HOW_TO_SUPPLY.get(m, f"Add {m}.") for m in missing),
                    params={"missing": missing},
                ),
            )
        return GateResult(gate_id="G6", decision="PASS", diagnostics=diagnostics)
