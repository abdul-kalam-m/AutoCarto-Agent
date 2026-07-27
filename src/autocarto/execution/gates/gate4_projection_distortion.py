"""Gate 4: Projection Distortion (Tissot Indicatrix Areal Scale).

No planar projection preserves both area and shape simultaneously (the
fundamental result behind the Tissot indicatrix). An area-comparison map
(any choropleth encoding a density/rate/count variable by region size) in
a non-equal-area projection lies about magnitude: Web Mercator inflates
high-latitude polygons by a factor that grows without bound toward the
poles, making a county at 49N look far larger, relative to one at 25N,
than it actually is — directly corrupting the visual comparison the map
exists to support.

Method: sample a k x k graticule over the AOI bounding box; at each node,
``pyproj.Proj.get_factors`` returns the local Tissot ``areal_scale`` — the
ratio of projected area to true area at that infinitesimal point (1.0 =
no distortion). REJECT if the *maximum* areal exaggeration
``|areal_scale - 1|`` across the sampled graticule exceeds the configured
threshold, for maps whose purpose is area comparison. Maps whose purpose
is shape-preservation or distance are not gated on areal distortion
(their fitness criterion is different) but the measurement is still
reported in diagnostics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Tuple

import numpy as np
import pyproj

from autocarto.config import THRESHOLDS
from autocarto.contracts import GateResult, Prescription
from autocarto.execution.gates.gate1_crs import _infer_aoi_scale, _prescribed_epsg_for_scale

MapPurpose = Literal["area_comparison", "shape", "distance"]

# Candidate equal-area CRSs tried when ranking prescriptions, keyed by the
# same EPSG codes Gate 1 treats as equal-area (config.py / gate1_crs.py).
_CANDIDATE_EPSGS: Tuple[int, ...] = (5070, 3310, 3083, 8857, 6933)


def _sample_areal_scales(epsg: int, bounds_4326: Tuple[float, float, float, float], resolution: int) -> np.ndarray:
    minx, miny, maxx, maxy = bounds_4326
    lons = np.linspace(minx, maxx, resolution)
    lats = np.linspace(miny, maxy, resolution)
    proj = pyproj.Proj(f"EPSG:{epsg}")

    scales: List[float] = []
    for lat in lats:
        for lon in lons:
            try:
                factors = proj.get_factors(lon, lat)
                s = float(factors.areal_scale)
                if np.isfinite(s) and s > 0:
                    scales.append(s)
            except Exception:
                continue  # graticule node outside this projection's valid domain
    return np.array(scales, dtype=float)


class ProjectionDistortionGate:
    """Gate 4: rejects area-comparison maps whose projection exceeds the
    configured areal-exaggeration threshold anywhere over the AOI."""

    def evaluate(
        self,
        target_epsg: int,
        aoi_bounds_4326: Tuple[float, float, float, float],
        map_purpose: MapPurpose = "area_comparison",
        graticule_resolution: int = THRESHOLDS.gate4.graticule_resolution,
    ) -> GateResult:
        scales = _sample_areal_scales(target_epsg, aoi_bounds_4326, graticule_resolution)

        if len(scales) == 0:
            return GateResult(
                gate_id="G4",
                decision="REJECT",
                diagnostics={"target_epsg": target_epsg, "sample_points": 0},
                instruction="No valid graticule samples in this projection's domain over the AOI.",
                prescription=Prescription(
                    method="reproject_equal_area",
                    instruction="Projection is not valid over this AOI at all; choose a different CRS.",
                    params={"candidates": self._rank_candidates(aoi_bounds_4326, graticule_resolution)},
                ),
            )

        exaggeration = np.abs(scales - 1.0)
        max_exag = float(exaggeration.max())
        mean_exag = float(exaggeration.mean())

        diagnostics: Dict[str, Any] = {
            "target_epsg": target_epsg,
            "map_purpose": map_purpose,
            "max_areal_exaggeration": round(max_exag, 4),
            "mean_areal_exaggeration": round(mean_exag, 4),
            "sample_points": int(len(scales)),
        }

        if map_purpose != "area_comparison":
            return GateResult(
                gate_id="G4",
                decision="PASS",
                diagnostics=diagnostics,
                instruction=(
                    f"Map purpose '{map_purpose}' does not require areal equivalence; "
                    f"distortion measured (max {max_exag:.1%}) but not gating."
                ),
            )

        if max_exag > THRESHOLDS.gate4.max_areal_exaggeration:
            candidates = self._rank_candidates(aoi_bounds_4326, graticule_resolution)
            best_epsg, best_exag = candidates[0]
            return GateResult(
                gate_id="G4",
                decision="REJECT",
                diagnostics=diagnostics,
                instruction=(
                    f"EPSG:{target_epsg} exceeds the areal-exaggeration threshold "
                    f"({max_exag:.1%} > {THRESHOLDS.gate4.max_areal_exaggeration:.0%}) "
                    f"for an area-comparison map."
                ),
                prescription=Prescription(
                    method="reproject_equal_area",
                    instruction=(
                        f"Reproject to EPSG:{best_epsg} (measured max residual "
                        f"distortion {best_exag:.2%} over this AOI)."
                    ),
                    params={"target_epsg": best_epsg, "candidates": candidates},
                    code_snippet=f"gdf = gdf.to_crs(epsg={best_epsg})",
                ),
            )

        return GateResult(gate_id="G4", decision="PASS", diagnostics=diagnostics)

    @staticmethod
    def _rank_candidates(
        bounds_4326: Tuple[float, float, float, float], resolution: int,
    ) -> List[Tuple[int, float]]:
        """Measured max areal exaggeration for each equal-area candidate, sorted best-first."""
        ranked: List[Tuple[int, float]] = []
        for epsg in _CANDIDATE_EPSGS:
            scales = _sample_areal_scales(epsg, bounds_4326, resolution)
            if len(scales) == 0:
                continue
            max_exag = float(np.abs(scales - 1.0).max())
            ranked.append((epsg, round(max_exag, 4)))
        ranked.sort(key=lambda pair: pair[1])
        if not ranked:
            # Degenerate fallback: scale-inferred default, unmeasured.
            scale = _infer_aoi_scale(bounds_4326)
            ranked.append((_prescribed_epsg_for_scale(scale), float("nan")))
        return ranked
