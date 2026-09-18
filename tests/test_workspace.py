"""Phase 0 contracts: round trips, untrusted imports, traces, and polygon provenance."""
from copy import deepcopy
import json

import pytest
from jsonschema import Draft202012Validator
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from autocarto.traces import differences, parse_document, schema, validate_document
from autocarto.web.app import app
from autocarto.web.engine import park_plan, read_data
from autocarto.web.workspace import dataset_versions, import_workspace, web_trace

client = TestClient(app)


@pytest.fixture
def workspace():
    settings = {"metric": "income", "palette": "violet", "method": "quantile"}
    return {"kind": "workspace", "version": 2, "datasets": dataset_versions(), "settings": settings,
            "parks": True, "visible": False, "opacity": 43, "outlines": False, "basemap": "satellite",
            "view": {"center": [-74.2, 40.7], "zoom": 9.3, "bearing": 12, "pitch": 20, "selected_county": "34013"},
            "messages": [{"id": 1, "role": "user", "content": "Map household income with parks"}, {"id": 2, "role": "assistant", "content": "Mapped income."}],
            "trace": web_trace(settings)}


def test_schema_is_valid_and_api_serves_same_contract(workspace):
    Draft202012Validator.check_schema(schema())
    Draft202012Validator(schema()).validate(workspace)
    assert client.get("/api/workspace/schema").json() == schema()


def test_workspace_roundtrip_preserves_complete_state(workspace):
    restored = client.post("/api/workspace/import", json=workspace)
    assert restored.status_code == 200, restored.text
    assert restored.json() == workspace
    assert import_workspace(parse_document(json.dumps(restored.json()).encode())) == workspace


def test_v3_point_layer_roundtrip_and_version_binding(workspace):
    workspace.update(version=3, park_points=True, datasets=dataset_versions(3))
    assert import_workspace(workspace) == workspace
    assert client.post("/api/workspace/import", json=workspace).json() == workspace
    workspace["datasets"]["park_points"]["sha256"] = "a" * 64
    with pytest.raises(ValueError, match="Dataset version mismatch"):
        import_workspace(workspace)


def test_historical_points_remain_separate_from_current_polygons():
    points = read_data("park_points")["features"]
    assert len(points) == 394
    assert all(f["geometry"]["type"] == "Point" for f in points)
    assert len(read_data("parks")["features"]) == 376
    manifest = read_data("manifest")
    assert manifest["sources"]["park_points"].endswith("/5")
    assert "2016" in manifest["coverage"]["park_points"]
    assert "not verified" in manifest["coverage"]["park_points"]


def test_v4_filters_and_drawing_order_roundtrip(workspace):
    workspace.update(version=4, park_points=True, datasets=dataset_versions(4),
                     county_filter=["34013", "34017"],
                     layer_order=["parks", "counties", "park_points"])
    response = client.post("/api/workspace/import", json=workspace)
    assert response.status_code == 200, response.text
    assert response.json() == workspace
    # Importing a display filter must not reclassify the statewide values.
    assert response.json()["trace"] == web_trace(workspace["settings"])


@pytest.mark.parametrize("field,value", [
    ("county_filter", ["34999"]),
    ("county_filter", ["34013", "34013"]),
    ("layer_order", ["parks", "parks", "counties"]),
    ("layer_order", ["parks", "counties"]),
    ("layer_order", ["parks", "counties", "unknown"]),
])
def test_v4_rejects_invalid_filters_and_drawing_order(workspace, field, value):
    workspace.update(version=4, park_points=True, datasets=dataset_versions(4),
                     county_filter=[], layer_order=["counties", "parks", "park_points"])
    workspace[field] = value
    assert client.post("/api/workspace/import", json=workspace).status_code == 422


@pytest.mark.parametrize("key,value", [("version", 99), ("version", True), ("kind", "unknown"), ("opacity", -1), ("opacity", 101), ("parks", "true"), ("basemap", "https://evil.test/tiles"), ("extra", "ignored?")])
def test_import_rejects_invalid_state(workspace, key, value):
    workspace[key] = value
    assert client.post("/api/workspace/import", json=workspace).status_code == 422


@pytest.mark.parametrize("target", ["datasets", "trace", "view"])
def test_import_rejects_mismatches_and_tampering(workspace, target):
    if target == "datasets":
        workspace["datasets"]["parks"]["sha256"] = "a" * 64
    elif target == "trace":
        workspace["trace"]["plan"]["colors"][0] = "#ff0000"
    else:
        workspace["view"]["selected_county"] = "34999"
    response = client.post("/api/workspace/import", json=workspace)
    assert response.status_code == 422


def test_import_rejects_modified_parks_trace(workspace):
    workspace["trace"]["parks"]["categories"][0]["color"] = "#ffffff"
    assert client.post("/api/workspace/import", json=workspace).status_code == 422


def test_browser_number_serialization_does_not_break_roundtrip(workspace):
    # JSON.stringify writes 0.0 as 0. JSON numeric equality is intentional,
    # but a boolean masquerading as a number must still differ.
    def js_numbers(value):
        if type(value) is float and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {k: js_numbers(v) for k, v in value.items()}
        if isinstance(value, list):
            return [js_numbers(v) for v in value]
        return value
    assert import_workspace(js_numbers(workspace)) == workspace
    assert differences(1, True)


@pytest.mark.parametrize("raw", [b"{", b"[]", b'{"kind":"workspace","kind":"workspace","version":2}', b'{"version":1}', b'{"kind":"workspace","version":NaN}'])
def test_invalid_documents_are_actionable_422(raw):
    response = client.post("/api/workspace/import", content=raw)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_import_has_separate_bounded_payload_budget(workspace):
    workspace["messages"] = [{"id": i, "role": "user", "content": "x" * 1000} for i in range(30)]
    assert client.post("/api/workspace/import", json=workspace).status_code == 200
    assert client.post("/api/chat", content=b" " * 16385).status_code == 413
    assert client.post("/api/workspace/import", content=b" " * (1024 * 1024 + 1)).status_code == 413
    # No Content-Length (chunked transfer) must not bypass the bound.
    assert client.post("/api/workspace/import", content=iter([b" " * 600000, b" " * 600000])).status_code == 413


def test_trace_is_audit_only_and_import_never_executes_chat(workspace, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("Import must never call an LLM")
    monkeypatch.setattr("autocarto.web.engine.WebIntentClient.parse", forbidden)
    workspace["messages"][0]["content"] = "<script>fetch('https://evil.test')</script>"
    assert import_workspace(workspace)["messages"] == workspace["messages"]
    assert client.post("/api/workspace/import", json=workspace["trace"]).status_code == 422


def test_diff_is_stable_precise_and_timing_ignore_is_explicit(workspace):
    changed = deepcopy(workspace)
    changed["opacity"] = 44
    assert differences(workspace, changed) == [{"path": "/opacity", "change": "changed", "before": 43, "after": 44}]
    assert differences({"a/b": 1}, {"a/b": 2})[0]["path"] == "/a~1b"
    assert differences({"execution_time_ms": 1}, {"execution_time_ms": 2})
    assert not differences({"execution_time_ms": 1}, {"execution_time_ms": 2}, ignore_timing=True)


def test_parks_snapshot_and_categorical_validation():
    from shapely.geometry import shape
    features = read_data("parks")["features"]
    manifest = read_data("manifest")
    assert manifest["sources"]["parks"].endswith("/67")
    assert manifest["manifest_version"] == 2
    assert len(features) == 376
    assert all(f["geometry"]["type"] in {"Polygon", "MultiPolygon"} and shape(f["geometry"]).is_valid and not shape(f["geometry"]).is_empty for f in features)
    assert all({"FEATURE_CLASS", "USE_DESIGNATION", "FACILITY_URL", "PUBLIC_ACCESS"} <= f["properties"].keys() for f in features)
    plan = park_plan()
    assert plan["field"] == "FEATURE_CLASS"
    assert sum(c["count"] for c in plan["categories"]) == 376
    assert all(g["gate"] == "G5" and g["passed"] for g in plan["validation"]["trace"])
    assert plan["dataset_sha256"] == manifest["files"]["parks.geojson"]["sha256"]


def test_single_color_gate_trace_is_standard_json():
    from autocarto.execution.gates.gate5_color_accessibility import ColorAccessibilityGate
    gate = ColorAccessibilityGate().evaluate(["#237d55"]).to_dict()
    json.dumps(gate, allow_nan=False)
    assert all(v is None for v in gate["diagnostics"]["min_delta_e_by_cvd_type"].values())


def test_cli_trace_contract_covers_human_review():
    trace = {"kind": "orchestrator-trace", "version": 1, "prompt": "unsupported", "dataset_id": "test", "seed": 0, "max_iter": 3, "iterations": [], "human_review": True, "intent_unresolved": True, "insufficiency_report": "Unavailable"}
    assert validate_document(trace) == trace


def test_cli_diff_and_validation_exit_codes(workspace, tmp_path, monkeypatch, capsys):
    from autocarto.traces.__main__ import main
    before, after = tmp_path / "before.json", tmp_path / "after.json"
    before.write_text(json.dumps(workspace), encoding="utf-8")
    after.write_text(json.dumps(workspace), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["traces", "validate", str(before)])
    assert main() == 0
    monkeypatch.setattr("sys.argv", ["traces", "diff", str(before), str(after)])
    assert main() == 0
    workspace["opacity"] = 66
    after.write_text(json.dumps(workspace), encoding="utf-8")
    assert main() == 1
    assert "/opacity" in capsys.readouterr().out
    after.write_text("{", encoding="utf-8")
    assert main() == 2
