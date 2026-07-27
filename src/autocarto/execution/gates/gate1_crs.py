"""Gate 1: CRS Integrity & Map-Type Appropriateness.

The first gate in execution order (contracts.GATE_ORDER) because every
downstream statistic — Gate 2's classification, Gate 3a/3b's spatial
weights, Gate 4's distortion measurement — silently assumes the geometry's
CRS is sane. A choropleth of "cases per square kilometre" computed while
the GeoDataFrame is still in EPSG:4326 (degrees) produces areas that are
not areas: a degree of longitude is ~111 km at the equator and ~0 km at
the poles, so every "area" in the density calculation is wrong by a
latitude-dependent factor Gate 1 exists to catch before it propagates.

Checks (Blueprint §3.1):
    (a) CRS present, and single across any joined GeoDataFrames
    (b) geographic CRS (lat/lon) flagged when areal computation follows
    (c) equal-area CRS required for density/rate choropleths
    (d) linear unit sanity for projected CRSs

Gate 1 makes a *declarative* equal-area determination (EPSG whitelist
lookup) — cheap and deterministic. It is deliberately not the *measured*
distortion check; that is Gate 4's job (Tissot indicatrix sampling). A CRS
can pass Gate 1 (it is nominally equal-area) and still be flagged by Gate 4
for a specific AOI if the projection's parameters are poorly centered on it.
"""

from __future__ import annotations

from typing import Literal, Optional

import pyproj

from autocarto.contracts import GateResult, Prescription

VariableRole = Literal["density", "count", "rate", "ordinal"]
MapType = Literal["choropleth", "bivariate", "proportional_symbol"]

# EPSG codes known to be equal-area (declarative whitelist — see module
# docstring for why this is intentionally not a measured check).
EQUAL_AREA_EPSG = {
    5070,   # NAD83 / Conus Albers
    3310,   # NAD83 / California Albers
    3083,   # NAD83 / Texas Centric Albers Equal Area
    2163,   # US National Atlas Equal Area
    6933,   # WGS 84 / NSIDC EASE-Grid 2.0 Global
    8857,   # WGS 84 / Equal Earth Greenwich
    3577,   # GDA94 / Australian Albers
    9822,   # generic Albers Equal Area conic (parametrized instances)
    102003,  # USA Contiguous Albers Equal Area Conic (ESRI)
}

AREA_SENSITIVE_ROLES: frozenset = frozenset({"density", "rate"})


def _infer_aoi_scale(total_bounds_lonlat: tuple) -> Literal["state", "conus", "global"]:
    """Coarse AOI-scale heuristic from a WGS84 bounding box.

    Deliberately simple (longitude span only): < 5 degrees -> state-scale,
    < 60 degrees -> CONUS-scale, else global. Good enough to select an
    equal-area CRS *family*; Gate 4 does the precise distortion check for
    the actual chosen CRS against the actual AOI.
    """
    minx, _, maxx, _ = total_bounds_lonlat
    lon_span = float(maxx - minx)
    if lon_span < 5.0:
        return "state"
    if lon_span < 60.0:
        return "conus"
    return "global"


def _prescribed_epsg_for_scale(scale: str, state_fips: Optional[str] = None) -> int:
    from autocarto.config import STATE_EQUAL_AREA_CRS

    if scale == "global":
        return 8857  # Equal Earth
    if scale == "state" and state_fips:
        code = STATE_EQUAL_AREA_CRS.get(state_fips)
        if code:
            return code
    return 5070  # CONUS Albers — safe default for state/conus scale


class CRSIntegrityGate:
    """Gate 1: validates CRS presence, consistency, and area-appropriateness."""

    def evaluate(
        self,
        gdf,
        intended_map_type: MapType,
        variable_role: VariableRole,
        join_gdf=None,
        state_fips: Optional[str] = None,
    ) -> GateResult:
        """
        Args:
            gdf: primary GeoDataFrame (geopandas)
            intended_map_type: "choropleth" | "bivariate" | "proportional_symbol"
            variable_role: "density" | "count" | "rate" | "ordinal"
            join_gdf: optional second GeoDataFrame this one will be joined
                against (e.g. a second variable's source); triggers the
                mixed-CRS check
            state_fips: optional 2-letter state code to refine the
                equal-area CRS prescription at state scale
        """
        diagnostics: dict = {"intended_map_type": intended_map_type, "variable_role": variable_role}

        # (a) CRS present
        if gdf.crs is None:
            return GateResult(
                gate_id="G1",
                decision="REJECT",
                diagnostics=diagnostics,
                instruction="GeoDataFrame has no CRS assigned.",
                prescription=Prescription(
                    method="set_crs",
                    instruction=(
                        "No CRS is set on the input geometry. Cartographic operations "
                        "downstream (area, distance, reprojection) are undefined without one. "
                        "If the source data is known to be WGS84 lon/lat (the common case for "
                        "GeoJSON/TIGER), set it explicitly — do not guess a projected CRS."
                    ),
                    params={},
                    code_snippet="gdf = gdf.set_crs(epsg=4326, allow_override=False)",
                ),
            )

        # (a) mixed CRS across a join
        if join_gdf is not None and join_gdf.crs is not None and join_gdf.crs != gdf.crs:
            return GateResult(
                gate_id="G1",
                decision="REJECT",
                diagnostics={**diagnostics, "primary_crs": str(gdf.crs), "join_crs": str(join_gdf.crs)},
                instruction="Joined GeoDataFrames have mismatched CRSs.",
                prescription=Prescription(
                    method="reproject_join",
                    instruction=(
                        f"Primary geometry is {gdf.crs} but the join geometry is "
                        f"{join_gdf.crs}. A spatial join across mismatched CRSs silently "
                        f"produces wrong intersections (coordinates are compared as if "
                        f"they shared a datum/units when they do not)."
                    ),
                    params={"target_epsg": gdf.crs.to_epsg()},
                    code_snippet=f"join_gdf = join_gdf.to_crs(gdf.crs)",
                ),
            )

        crs = pyproj.CRS(gdf.crs)
        diagnostics["epsg"] = crs.to_epsg()
        diagnostics["is_geographic"] = crs.is_geographic

        area_sensitive = (
            variable_role in AREA_SENSITIVE_ROLES
            and intended_map_type in ("choropleth", "bivariate")
        )

        # (b) geographic CRS used where areal computation follows
        if area_sensitive and crs.is_geographic:
            bounds = tuple(gdf.total_bounds)
            scale = _infer_aoi_scale(bounds)
            epsg = _prescribed_epsg_for_scale(scale, state_fips)
            return GateResult(
                gate_id="G1",
                decision="REJECT",
                diagnostics={**diagnostics, "aoi_scale": scale},
                instruction=(
                    f"Variable role '{variable_role}' requires area computation, but the "
                    f"geometry is in a geographic CRS ({crs.name}, degrees). Area in "
                    f"degrees^2 is not a real areal unit and varies with latitude."
                ),
                prescription=Prescription(
                    method="reproject_equal_area",
                    instruction=(
                        f"Reproject to an equal-area CRS before computing any area-based "
                        f"variable. For this AOI's scale ({scale}), use EPSG:{epsg}."
                    ),
                    params={"target_epsg": epsg, "aoi_scale": scale},
                    code_snippet=f"gdf = gdf.to_crs(epsg={epsg})",
                ),
            )

        # (c) projected but not on the equal-area whitelist, for an area-sensitive role
        if area_sensitive and crs.is_projected and crs.to_epsg() not in EQUAL_AREA_EPSG:
            bounds_4326 = tuple(gdf.to_crs(epsg=4326).total_bounds)
            scale = _infer_aoi_scale(bounds_4326)
            epsg = _prescribed_epsg_for_scale(scale, state_fips)
            return GateResult(
                gate_id="G1",
                decision="REJECT",
                diagnostics={**diagnostics, "aoi_scale": scale},
                instruction=(
                    f"CRS {crs.name} (EPSG:{crs.to_epsg()}) is projected but not confirmed "
                    f"equal-area. Area-based variable role '{variable_role}' requires one."
                ),
                prescription=Prescription(
                    method="reproject_equal_area",
                    instruction=f"Reproject to EPSG:{epsg} (equal-area for this AOI's scale).",
                    params={"target_epsg": epsg, "aoi_scale": scale},
                    code_snippet=f"gdf = gdf.to_crs(epsg={epsg})",
                ),
            )

        # (d) linear unit sanity for projected CRSs (informational WARN only)
        if crs.is_projected:
            unit = crs.axis_info[0].unit_name if crs.axis_info else "unknown"
            diagnostics["linear_unit"] = unit
            if unit not in ("metre", "meter", "meters"):
                return GateResult(
                    gate_id="G1",
                    decision="WARN",
                    diagnostics=diagnostics,
                    instruction=(
                        f"Projected CRS uses linear unit '{unit}', not metres. Area/distance "
                        f"computations will be correct but reported in non-metric units — "
                        f"verify downstream unit conversions are applied."
                    ),
                )

        return GateResult(gate_id="G1", decision="PASS", diagnostics=diagnostics)
