"""Local Compose acceptance check; synthetic accounts only, no external AI calls.

Run inside the local beta web container, never against production. Re-running
checks the existing saved map and quota before making a new unique test budget.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor
from autocarto.web.store import Store, StoreError, get_store, users
from autocarto.web.workspace import dataset_versions, web_trace
from sqlalchemy import select
import uuid

assert os.getenv("AUTOCARTO_DEPLOYMENT") != "production", "Local acceptance only"
store = get_store()
email = "browser-acceptance@example.test"
password = "local-beta-acceptance-password"
with store.engine.connect() as conn:
    existing = conn.execute(select(users.c.id).where(users.c.email == email)).scalar_one_or_none()
if not existing:
    store.register(email, password, store.invite(email))
opener = build_opener(HTTPCookieProcessor())
def call(path, data=None, method=None):
    request = Request("http://127.0.0.1:8000/api/" + path,
                      data=json.dumps(data).encode() if data is not None else None,
                      headers={"Content-Type": "application/json", "X-CartoLLM-Request": "1", "Origin": "http://127.0.0.1:8001"}, method=method)
    with opener.open(request) as response:
        return json.load(response)

user = call("auth/login", {"email": email, "password": password})["user"]
assert call("catalog")["datasets"]
settings = {"metric": "income", "palette": "violet", "method": "quantile"}
workspace = {"kind": "workspace", "version": 3, "datasets": dataset_versions(3), "settings": settings,
             "parks": True, "park_points": True, "visible": True, "opacity": 85, "outlines": True,
             "basemap": "satellite", "view": {"center": [-74.2, 40.7], "zoom": 9, "bearing": 0, "pitch": 0, "selected_county": "34013"},
             "messages": [{"id": 1, "role": "user", "content": "Map household income"}], "trace": web_trace(settings)}
projects = call("projects")
if projects:
    saved = call("projects/" + projects[0]["id"])
    assert saved["workspace"]["kind"] == "workspace"
    print("Previously saved workspace survived server restart")
else:
    saved = call("projects", {"name": "Beta acceptance map", "workspace": workspace})
assert call("projects/" + saved["id"])["workspace"]["version"] == 3
try:
    call("projects/" + saved["id"], {"name": "Stale write", "revision": 0, "workspace": workspace}, "PUT")
    raise AssertionError("Stale revision accepted")
except HTTPError as error:
    assert error.code == 409
other = Store(os.environ["DATABASE_URL"])
budget_owner = str(uuid.uuid4())
def consume(i):
    try:
        (store if i % 2 else other).consume_ai(budget_owner, 5)
        return True
    except StoreError as error:
        assert error.status == 429
        return False
with ThreadPoolExecutor(max_workers=8) as pool:
    assert sum(pool.map(consume, range(20))) == 5
assert other.quota(budget_owner, 5)["remaining"] == 0
assert store.list_projects("unrelated-user") == []
try:
    store.project("unrelated-user", saved["id"])
    raise AssertionError("Cross-user read allowed")
except StoreError as error:
    assert error.status == 404
call("auth/logout", {})
try:
    call("projects")
    raise AssertionError("Logged-out read allowed")
except HTTPError as error:
    assert error.code == 401
print("PASS: PostgreSQL persistence, isolation, revision conflicts, cookie sessions, and 20 competing quota calls across two engines (exactly 5 admitted)")
