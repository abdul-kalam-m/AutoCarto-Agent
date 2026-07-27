"""Gate 4 (Tissot projection distortion) behavioral tests — Blueprint §3.3."""

from __future__ import annotations

import pytest

from autocarto.execution.gates.gate4_projection_distortion import ProjectionDistortionGate

CONUS_BOUNDS = (-125.0, 24.5, -66.9, 49.4)


def test_web_mercator_over_conus_rejected_for_area_comparison():
    res = ProjectionDistortionGate().evaluate(
        target_epsg=3857, aoi_bounds_4326=CONUS_BOUNDS,
        map_purpose="area_comparison", graticule_resolution=8,
    )
    assert res.decision == "REJECT"
    assert res.diagnostics["max_areal_exaggeration"] > 0.20
    assert res.prescription.method == "reproject_equal_area"


def test_albers_over_conus_passes():
    res = ProjectionDistortionGate().evaluate(
        target_epsg=5070, aoi_bounds_4326=CONUS_BOUNDS,
        map_purpose="area_comparison", graticule_resolution=8,
    )
    assert res.decision == "PASS"
    assert res.diagnostics["max_areal_exaggeration"] < 0.01


def test_web_mercator_ok_for_shape_purpose_but_still_measured():
    res = ProjectionDistortionGate().evaluate(
        target_epsg=3857, aoi_bounds_4326=CONUS_BOUNDS,
        map_purpose="shape", graticule_resolution=8,
    )
    assert res.decision == "PASS"
    # Still reports the real distortion even though it doesn't gate.
    assert res.diagnostics["max_areal_exaggeration"] > 0.20


def test_rejection_prescribes_lowest_distortion_candidate_first():
    res = ProjectionDistortionGate().evaluate(
        target_epsg=3857, aoi_bounds_4326=CONUS_BOUNDS,
        map_purpose="area_comparison", graticule_resolution=6,
    )
    candidates = res.prescription.params["candidates"]
    exaggerations = [exag for _epsg, exag in candidates]
    assert exaggerations == sorted(exaggerations)
    assert res.prescription.params["target_epsg"] == candidates[0][0]


def test_small_state_scale_aoi_albers_still_low_distortion():
    # Georgia-ish bbox
    ga_bounds = (-85.6, 30.4, -80.8, 35.0)
    res = ProjectionDistortionGate().evaluate(
        target_epsg=5070, aoi_bounds_4326=ga_bounds,
        map_purpose="area_comparison", graticule_resolution=6,
    )
    assert res.decision == "PASS"
