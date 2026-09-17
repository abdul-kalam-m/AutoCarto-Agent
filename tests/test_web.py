"""Web behavior, authority boundaries, snapshot provenance, and API validation."""
import hashlib
import itertools
import json

import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from autocarto.web.app import app
from autocarto.web.engine import DATA, ChatRequest, MapRequest, WebIntentClient, chat, plan, read_data

client = TestClient(app)


def test_pinned_catalog_is_complete_and_integrity_checked():
    manifest = read_data("manifest")
    for name, entry in manifest["files"].items():
        raw = (DATA / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        assert len(json.loads(raw)["features"]) == entry["features"]
    counties = read_data("counties")["features"]
    assert len(counties) == 21
    assert len({f["properties"]["id"] for f in counties}) == 21
    assert len(read_data("parks")["features"]) == 376
    for feature in counties:
        p = feature["properties"]
        assert p["income"] > 0
        assert p["density"] == pytest.approx(p["population"] / p["area_sq_miles"], abs=0.2)


@pytest.mark.parametrize("metric,palette,method", list(itertools.product(
    ["density", "population", "income"], ["forest", "ocean", "violet", "sunset"], ["auto", "jenks", "quantile", "equal_interval"]
)))
def test_every_map_combination_converges_and_covers_data(metric, palette, method):
    result = plan(MapRequest(metric=metric, palette=palette, method=method))
    values = [f["properties"][metric] for f in read_data("counties")["features"]]
    assert result["validation"]["classification"]["decision"] in {"PASS", "WARN"}
    assert result["validation"]["color"]["decision"] == "PASS"
    assert len(result["breaks"]) == len(result["colors"]) + 1
    assert all(a < b for a, b in zip(result["breaks"], result["breaks"][1:]))
    assert result["breaks"][0] <= min(values)
    assert result["breaks"][-1] >= max(values)
    assert result["plan_id"] == plan(MapRequest(metric=metric, palette=palette, method=method))["plan_id"]


def test_guided_chat_preserves_current_context_and_adds_parks():
    result = chat(ChatRequest(message="Add parks", current=MapRequest(metric="income", palette="violet")))
    assert result["applied"] and result["parks"]
    assert result["settings"]["metric"] == "income"
    assert result["settings"]["palette"] == "violet"
    assert result["provider"]["provider"] == "guided"


def test_county_focus_does_not_claim_filtering():
    result = chat(ChatRequest(message="Show income in Essex County"))
    assert result["county"] == "Essex"
    assert result["map"]["summary"]["count"] == 21
    assert "still uses all 21" in result["message"]


@pytest.mark.parametrize("message", ["Show flood risk", "Map income above $100,000", "Compare population and income", "Map income by tract", "Show hospital access", "Map 2025 population", "Tell me the weather", "Map population in California", "Map income in Newark", "Show income and population"])
def test_unsupported_requests_do_not_change_map(message):
    result = chat(ChatRequest(message=message))
    assert result["applied"] is False
    assert "map" not in result


def test_ai_receives_schema_never_feature_values(monkeypatch):
    captured = {}
    def transport(self, system, user):
        captured["system"] = system
        captured["user"] = user
        return '{"action":"map","metric":"income","parks":true}'
    monkeypatch.setattr(WebIntentClient, "_chat", transport)
    client = WebIntentClient(api_key="test-key")
    intent, record = client.parse("Map income and parks", MapRequest())
    assert intent.metric == "income"
    assert "dataset_schemas" in captured["system"]
    assert "coordinates" not in captured["system"]
    assert str(read_data("counties")["features"][0]["properties"]["income"]) not in captured["system"]
    assert len(record["prompt_hash"]) == 64


def test_ai_failure_does_not_silently_substitute(monkeypatch):
    monkeypatch.setattr("autocarto.web.engine.get_key", lambda *a, **k: "test-key")
    def fail(*a, **k):
        raise RuntimeError("Provider secret-key internal failure")
    monkeypatch.setattr(WebIntentClient, "parse", fail)
    with pytest.raises(ValueError, match="could not resolve") as error:
        chat(ChatRequest(message="Map income", use_ai=True))
    assert "secret-key" not in str(error.value)


def test_web_uses_its_own_model_default_and_structured_request(monkeypatch):
    client = WebIntentClient(api_key="test-key")
    assert client.model == WebIntentClient.DEFAULT_MODEL
    assert client.version == "web-intent-v1"
    captured = {}
    def stream(body):
        captured.update(body)
        return '{"action":"map","metric":"income"}'
    monkeypatch.setattr(client, "_stream_once", stream)
    assert client.parse("Map income", MapRequest())[0].metric == "income"
    assert captured["chat_template_kwargs"]["enable_thinking"] is False
    assert captured["temperature"] == 0


def test_offline_mode_refuses_ai(monkeypatch):
    monkeypatch.setenv("AUTOCARTO_OFFLINE", "1")
    with pytest.raises(ValueError, match="unavailable"):
        chat(ChatRequest(message="Map income", use_ai=True))
    assert client.get("/api/catalog").json()["offline"]


def test_http_contract_and_path_allowlist():
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/data/counties").json()["type"] == "FeatureCollection"
    assert client.get("/api/data/secrets").status_code == 404
    assert client.post("/api/map", json={"metric": "made_up"}).status_code == 422
    assert client.post("/api/map", json={"breaks": [1, 99]}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 1501}).status_code == 422
    assert client.post("/api/chat", json={"message": " "}).status_code == 422
    response = client.post("/api/map", json={"metric": "income"})
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "G2" == response.json()["validation"]["classification"]["gate"]


def test_payload_cannot_execute_model_code():
    response = client.post("/api/chat", json={"message": "exec('malicious code')"})
    assert response.status_code == 200
    assert not response.json()["applied"]


def test_ocean_county_is_not_a_palette_change():
    result = chat(ChatRequest(message="Show income in Ocean County", current=MapRequest(palette="violet")))
    assert result["county"] == "Ocean"
    assert result["settings"]["palette"] == "violet"


@pytest.mark.parametrize("message", ["Show population density across New Jersey", "Map household income in New Jersey", "Show park locations in New Jersey", "Which county has the highest income?"])
def test_ui_starting_points_and_basic_questions(message):
    assert chat(ChatRequest(message=message))["applied"]


def test_classification_matches_right_inclusive_renderer_bins():
    result = plan(MapRequest(metric="income"))
    for i, boundary in enumerate(result["breaks"][1:-1]):
        assigned = int(np.digitize(boundary, result["breaks"][1:-1], right=True))
        assert assigned == i
