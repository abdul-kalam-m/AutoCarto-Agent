"""Private beta boundaries: shared state, ownership, sessions and quotas."""
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from fastapi.testclient import TestClient
from autocarto.web.app import app
from autocarto.web.store import Store, StoreError, get_store
from autocarto.web.workspace import dataset_versions, web_trace
from autocarto.web.monitoring import scrub_event
from autocarto.traces import validate_document


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "beta.db"))
    monkeypatch.setenv("AUTOCARTO_AUTH_REQUIRED", "1")
    monkeypatch.setenv("AUTOCARTO_PUBLIC_URL", "http://testserver")
    monkeypatch.delenv("AUTOCARTO_DEPLOYMENT", raising=False)
    value = get_store()
    value.migrate()
    return value


def enroll(store, email="one@example.test"):
    token = store.register(email, "twelve-characters-password", store.invite(email))
    return token, store.user(token)


def document():
    settings = {"metric": "income", "palette": "forest", "method": "auto"}
    return {"kind": "workspace", "version": 2, "datasets": dataset_versions(), "settings": settings,
            "parks": True, "visible": True, "opacity": 85, "outlines": True, "basemap": "light",
            "view": {"center": [-74.5, 40], "zoom": 7, "bearing": 0, "pitch": 0, "selected_county": None},
            "messages": [], "trace": web_trace(settings)}


def test_invitation_single_use_and_logout(store):
    invite = store.invite("one@example.test")
    token = store.register("ONE@example.test", "test-password-long", invite)
    assert store.user(token)["email"] == "one@example.test"
    with pytest.raises(StoreError, match="Invitation"):
        store.register("one@example.test", "test-password-long", invite)
    store.logout(token)
    assert store.user(token) is None
    assert store.user(store.login("one@example.test", "test-password-long"))
    with pytest.raises(StoreError) as rejected:
        store.login("unknown@example.test", "test-password-long")
    assert rejected.value.status == 401


def test_expired_invitation(store):
    with pytest.raises(StoreError, match="Invitation"):
        store.register("expired@example.test", "test-password-long", store.invite("expired@example.test", lifetime=-1))


def test_shared_quota_atomic_across_engines(store):
    _, user = enroll(store)
    other = Store(str(store.engine.url))
    def consume(i):
        try:
            (store if i % 2 else other).consume_ai(user["id"], 5)
            return True
        except StoreError as error:
            assert error.status == 429
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(consume, range(20))) == 5
    assert other.quota(user["id"], 5)["remaining"] == 0
    _, second = enroll(store, "two@example.test")
    other.consume_ai(second["id"], 5)
    assert store.quota(second["id"], 5)["used"] == 1
    other.engine.dispose()


def test_owned_projects_persist_and_conflicts(store):
    _, user = enroll(store)
    _, other = enroll(store, "two@example.test")
    saved = store.save(user["id"], None, "My map", document(), 0)
    restarted = Store(str(store.engine.url))
    assert restarted.project(user["id"], saved["id"])["workspace"] == document()
    assert restarted.list_projects(other["id"]) == []
    with pytest.raises(StoreError) as rejected:
        restarted.project(other["id"], saved["id"])
    assert rejected.value.status == 404
    store.save(user["id"], saved["id"], "Changed", document(), 1)
    with pytest.raises(StoreError) as conflict:
        restarted.save(user["id"], saved["id"], "Stale", document(), 1)
    assert conflict.value.status == 409
    restarted.engine.dispose()


def test_authenticated_api_roundtrip_csrf_and_isolation(store):
    with TestClient(app) as client:
        assert client.get("/api/catalog").status_code == 401
        credentials = {"email": "api@example.test", "password": "test-password-long", "invitation": store.invite("api@example.test")}
        assert client.post("/api/auth/register", json=credentials).status_code == 403
        headers = {"X-CartoLLM-Request": "1", "Origin": "http://testserver"}
        registered = client.post("/api/auth/register", json=credentials, headers=headers)
        assert registered.status_code == 200, registered.text
        assert "HttpOnly" in registered.headers["set-cookie"]
        assert client.get("/api/catalog").status_code == 200
        created = client.post("/api/projects", json={"name": "Income", "workspace": document()}, headers=headers)
        assert created.status_code == 200, created.text
        identifier = created.json()["id"]
        assert client.get(f"/api/projects/{identifier}").json()["workspace"] == document()
        assert client.post("/api/auth/logout", json={}, headers={**headers, "Origin": "https://evil.test"}).status_code == 403
        assert client.post("/api/auth/logout", json={}, headers=headers).status_code == 200
        assert client.get(f"/api/projects/{identifier}").status_code == 401
        assert client.post("/api/auth/login", json={"email": credentials["email"], "password": credentials["password"]}, headers=headers).status_code == 200
        assert client.get("/api/projects").json()[0]["id"] == identifier
        assert client.post("/api/chat", content=b"x" * 16385, headers=headers).status_code == 413


def test_monitoring_drops_private_payload():
    event = {"request": {"data": "private prompt"}, "user": {"email": "private"}, "extra": {"password": "secret"}, "exception": {"values": [{"value": "secret", "stacktrace": {"frames": [{"vars": {"token": "secret"}, "filename": "app.py"}]}}]}}
    sanitized = scrub_event(event, {})
    assert "secret" not in json.dumps(sanitized)
    assert "private" not in json.dumps(sanitized)


@pytest.mark.parametrize("value", [{}, {"version": 1}, {"kind": []}])
def test_unrelated_json_not_misdiagnosed_as_legacy(value):
    with pytest.raises(ValueError) as error:
        validate_document(value)
    assert "Legacy" not in str(error.value)
