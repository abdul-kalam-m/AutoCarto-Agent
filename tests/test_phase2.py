"""Phase 2: actual snapshot joins, operation rejection, persistence and bounds."""
import json
import geopandas as gpd
import pytest
from shapely.geometry import Point, box
from fastapi.testclient import TestClient
from autocarto.web.app import app
from autocarto.web.engine import read_data, _plan
from autocarto.web.spatial import ProximityRequest, proximity, map_geometry_checks
from autocarto.web.workspace import dataset_versions, web_trace, import_workspace
from autocarto.execution.gates.gate7_buffer import BufferGate
from autocarto.execution.gates.gate8_spatial_join import SpatialJoinGate

client = TestClient(app)


def test_tract_snapshot_geometry_coverage_missing_values():
    data = read_data("tracts")
    frame = gpd.GeoDataFrame.from_features(data["features"], crs=4326)
    assert len(frame) == frame.id.nunique() == 2181
    assert frame.geometry.is_valid.all()
    assert frame.population.isna().sum() == 0
    assert frame.income.isna().sum() == 27
    assert frame.density.isna().sum() == 6
    assert frame.id.str.startswith("34").all()


@pytest.mark.parametrize("metric", ["income", "population", "density"])
def test_tract_classification_excludes_missing_not_zero(metric):
    plan = _plan(metric, "forest", "auto", "tracts")
    assert plan["summary"]["count"] + plan["summary"]["missing"] == 2181
    assert plan["validation"]["classification"]["passed"]
    assert plan["validation"]["color"]["passed"]
    json.dumps(plan, allow_nan=False)


def test_point_buffer_intersection_actual_snapshot():
    result = proximity(ProximityRequest(distance_m=500))
    assert result["applied"]
    assert len(result["buffers"]["features"]) == 394
    record = result["record"]
    from autocarto.traces import validate_document
    assert validate_document(record) == record
    assert len(record["matched_tract_ids"]) == len(set(record["matched_tract_ids"])) == 790
    assert record["source"] == "park_points"
    assert [(g["gate"], g["decision"]) for g in record["trace"]] == [("G7", "WARN"), ("G1", "PASS"), ("G4", "PASS"), ("G8", "PASS")]
    # Independent brute force check on a county, not the indexed join implementation.
    subset = proximity(ProximityRequest(distance_m=500, counties=["34013"]))
    tracts = gpd.GeoDataFrame.from_features(read_data("tracts")["features"], crs=4326).to_crs(32111)
    tracts = tracts[tracts.county_id == "34013"]
    points = gpd.GeoDataFrame.from_features(read_data("park_points")["features"], crs=4326).to_crs(32111)
    buffers = points.geometry.buffer(500, resolution=32)
    expected = sorted(row.id for _, row in tracts.iterrows() if any(row.geometry.intersects(b) for b in buffers))
    assert subset["record"]["matched_tract_ids"] == expected


@pytest.mark.parametrize("distance", [-1, 0, 10001, float("nan")])
def test_buffer_rejects_invalid_distance(distance):
    points = gpd.GeoDataFrame(geometry=[Point(-74.2, 40.7)], crs=4326).to_crs(32111)
    gate = BufferGate().evaluate(points, distance, "exploratory_proximity")
    assert gate.decision == "REJECT" and gate.prescription


def test_buffer_rejects_polygons_wrong_crs_and_access_claims():
    polygon = gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs=32111)
    assert BufferGate().evaluate(polygon, 500, "exploratory_proximity").decision == "REJECT"
    points = gpd.GeoDataFrame(geometry=[Point(-74.2, 40.7)], crs=4326)
    assert BufferGate().evaluate(points, 500, "exploratory_proximity").decision == "REJECT"
    assert BufferGate().evaluate(points.to_crs(32111), 500, "walking_access").decision == "REJECT"
    response = client.post("/api/proximity", json={"source": "parks", "distance_m": 500}).json()
    assert not response["applied"] and response["trace"][0]["gate"] == "G7"


def test_spatial_join_rejects_incomplete_mixed_crs_duplicate_ids():
    polygons = gpd.GeoDataFrame(geometry=[box(0, 0, 10, 10)], crs=32111)
    gate = SpatialJoinGate()
    assert gate.evaluate(polygons, polygons).passed
    assert not gate.evaluate(polygons, polygons, complete=False).passed
    assert not gate.evaluate(polygons, polygons.to_crs(4326)).passed
    assert not gate.evaluate(polygons, polygons, predicate="within").passed
    duplicate = gpd.GeoDataFrame(geometry=[box(0, 0, 10, 10)] * 2, crs=32111, index=["a", "a"])
    assert not gate.evaluate(duplicate, polygons).passed


def test_display_gates_do_not_certify_web_mercator():
    for dataset in ("counties", "tracts"):
        assert [(g["gate"], g["decision"]) for g in map_geometry_checks(dataset)] == [("G1", "REJECT"), ("G4", "REJECT")]
    assert map_geometry_checks("tracts", "income")[0]["diagnostics"]["variable_role"] == "ordinal"
    assert map_geometry_checks("tracts", "population")[0]["diagnostics"]["variable_role"] == "count"
    assert client.post("/api/render-check", json={}).json()["decision"] == "REJECT"
    complete = {"title": "NJ population", "legend_present": True, "scale_bar_present": True, "data_citation": "Census ACS", "crs_note": "EPSG:3857", "classification_note": "Natural breaks"}
    assert client.post("/api/render-check", json=complete).json()["decision"] == "PASS"


def test_v5_roundtrip_binds_proximity_result():
    settings = {"metric": "income", "palette": "forest", "method": "auto"}
    record = proximity(ProximityRequest(distance_m=500))["record"]
    workspace = {"kind": "workspace", "version": 5, "datasets": dataset_versions(5), "settings": settings,
                 "parks": False, "park_points": True, "visible": True, "opacity": 85, "outlines": True, "basemap": "light",
                 "view": {"center": [-74.2, 40.7], "zoom": 9, "bearing": 0, "pitch": 0, "selected_county": None},
                 "messages": [], "trace": web_trace(settings), "county_filter": [], "layer_order": ["counties", "parks", "park_points"],
                 "phase2": {"tracts": True, "tract_plan_id": _plan(**settings, dataset="tracts")["plan_id"], "distance_m": 500, "result_id": record["result_id"], "overlays": ["roads"]}}
    assert import_workspace(workspace) == workspace
    assert client.post("/api/workspace/import", json=workspace).json() == workspace
    workspace["phase2"]["tract_plan_id"] = "a" * 16
    with pytest.raises(ValueError, match="tract classification"):
        import_workspace(workspace)
    workspace["phase2"]["tract_plan_id"] = _plan(**settings, dataset="tracts")["plan_id"]
    workspace["phase2"]["distance_m"] = 600
    with pytest.raises(ValueError, match="proximity"):
        import_workspace(workspace)


def test_reference_query_rejects_unbounded_or_unknown_inputs():
    assert len(client.get("/api/reference-layers").json()) == 5
    for name, bounds in [("arbitrary-url", [-74.2, 40.7, -74.19, 40.71]), ("parcels", [-75.6, 38.9, -73.9, 41.3])]:
        assert client.post(f"/api/reference-layers/{name}", json={"bounds": bounds}).status_code == 422


def test_reference_query_refuses_truncation(monkeypatch):
    from autocarto.web import overlays
    monkeypatch.setattr(overlays, "metadata", lambda _: {"fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID"}]})
    monkeypatch.setattr(overlays, "is_offline", lambda: False)
    monkeypatch.setattr(overlays, "_get", lambda *args: {"count": 2001})
    with pytest.raises(ValueError, match="no partial"):
        overlays.load("roads", [-74.2, 40.7, -74.19, 40.71])
