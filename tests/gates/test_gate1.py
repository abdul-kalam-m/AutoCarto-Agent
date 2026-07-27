"""Gate 1 (CRS integrity) behavioral tests — Blueprint §3.1 acceptance criteria."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import box

from autocarto.execution.gates.gate1_crs import CRSIntegrityGate


def _grid_gdf(n_side: int = 4, crs=None) -> gpd.GeoDataFrame:
    cells = [box(i, j, i + 1, j + 1) for i in range(n_side) for j in range(n_side)]
    return gpd.GeoDataFrame({"geometry": cells}, crs=crs)


def test_no_crs_rejected_with_set_crs_prescription():
    gdf = _grid_gdf(crs=None)
    res = CRSIntegrityGate().evaluate(gdf, "choropleth", "density")
    assert res.decision == "REJECT"
    assert res.prescription.method == "set_crs"


def test_geographic_crs_for_density_rejected_prescribes_5070():
    # A 4x4 unit-degree grid near the CONUS interior -> lon span < 60 -> CONUS scale
    gdf = _grid_gdf(crs="EPSG:4326")
    res = CRSIntegrityGate().evaluate(gdf, "choropleth", "density")
    assert res.decision == "REJECT"
    assert res.prescription.method == "reproject_equal_area"
    assert res.prescription.params["target_epsg"] == 5070


def test_geographic_crs_ok_for_ordinal_role():
    # Ordinal roles never need area -> geographic CRS is fine
    gdf = _grid_gdf(crs="EPSG:4326")
    res = CRSIntegrityGate().evaluate(gdf, "choropleth", "ordinal")
    assert res.decision == "PASS"


def test_already_equal_area_passes():
    gdf = _grid_gdf(crs="EPSG:4326").to_crs(epsg=5070)
    res = CRSIntegrityGate().evaluate(gdf, "choropleth", "density")
    assert res.decision == "PASS"
    assert res.diagnostics["epsg"] == 5070


def test_web_mercator_for_density_rejected_not_on_equal_area_whitelist():
    gdf = _grid_gdf(crs="EPSG:4326").to_crs(epsg=3857)
    res = CRSIntegrityGate().evaluate(gdf, "choropleth", "rate")
    assert res.decision == "REJECT"
    assert res.prescription.method == "reproject_equal_area"


def test_mixed_crs_join_rejected():
    gdf = _grid_gdf(crs="EPSG:5070")
    join = _grid_gdf(crs="EPSG:4326")
    res = CRSIntegrityGate().evaluate(gdf, "choropleth", "count", join_gdf=join)
    assert res.decision == "REJECT"
    assert res.prescription.method == "reproject_join"


def test_count_role_on_geographic_crs_passes_no_area_needed():
    gdf = _grid_gdf(crs="EPSG:4326")
    res = CRSIntegrityGate().evaluate(gdf, "choropleth", "count")
    assert res.decision == "PASS"


def test_global_scale_prescribes_equal_earth():
    # A geometry spanning > 60 degrees of longitude -> global scale -> EPSG:8857
    cells = [box(-170, -10, 170, 10)]
    gdf = gpd.GeoDataFrame({"geometry": cells}, crs="EPSG:4326")
    res = CRSIntegrityGate().evaluate(gdf, "choropleth", "density")
    assert res.decision == "REJECT"
    assert res.prescription.params["target_epsg"] == 8857
    assert res.prescription.params["aoi_scale"] == "global"
