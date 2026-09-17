"""Same-origin FastAPI service and compiled React workspace."""
from __future__ import annotations

import os
from pathlib import Path
from threading import BoundedSemaphore
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from autocarto.web.engine import ChatRequest, MapRequest, catalog, chat, plan, read_data
from autocarto.traces import MAX_DOCUMENT_BYTES, parse_document, schema
from autocarto.web.workspace import import_workspace
from autocarto.web.accounts import COOKIE, router as accounts_router
from autocarto.web.store import StoreError, ai_limit, auth_required, get_store, production
from autocarto.web.monitoring import configure as configure_monitoring, report_error


@asynccontextmanager
async def lifespan(app):
    if production():
        if not os.getenv("AUTOCARTO_PUBLIC_URL", "").startswith("https://"):
            raise RuntimeError("Production requires an HTTPS AUTOCARTO_PUBLIC_URL")
        if not os.getenv("SENTRY_DSN"):
            raise RuntimeError("Production requires SENTRY_DSN for error monitoring")
    if auth_required():
        get_store().ready()
    configure_monitoring()
    yield

app = FastAPI(title="CartoLLM web API", version="0.2.0", lifespan=lifespan, docs_url=None if production() else "/docs", redoc_url=None if production() else "/redoc")
app.include_router(accounts_router)
AI_SLOTS = BoundedSemaphore(2)


@app.middleware("http")
async def response_headers(request, call_next):
    try:
        length = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        return JSONResponse({"detail": "Invalid content length"}, status_code=400)
    path = request.url.path
    limit = MAX_DOCUMENT_BYTES + 4096 if path.startswith("/api/projects") else MAX_DOCUMENT_BYTES if path == "/api/workspace/import" else 16384
    if length > limit and request.method in {"POST", "PUT"}:
        return JSONResponse({"detail": "Request too large"}, status_code=413)
    # Read bounded bodies before FastAPI parses them; chunked transfer cannot
    # evade the body limit. Starlette replays the cached body downstream.
    if request.method in {"POST", "PUT"}:
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > limit:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
            body.extend(chunk)
        request._body = bytes(body)
    request.state.user = None
    try:
        if auth_required():
            if request.method in {"POST", "PUT", "DELETE"}:
                expected_origin = os.getenv("AUTOCARTO_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
                if request.headers.get("x-cartollm-request") != "1" or request.headers.get("origin", expected_origin) != expected_origin:
                    return JSONResponse({"detail": "Request origin check failed"}, status_code=403)
            token = request.cookies.get(COOKIE)
            if token:
                from starlette.concurrency import run_in_threadpool
                request.state.user = await run_in_threadpool(get_store().user, token)
            public = {"/api/health", "/api/auth/me", "/api/auth/login", "/api/auth/register"}
            if path.startswith("/api/") and path not in public and not request.state.user:
                return JSONResponse({"detail": "Sign in to continue"}, status_code=401)
        response = await call_next(request)
    except StoreError as error:
        response = JSONResponse({"detail": str(error)}, status_code=error.status)
    except Exception as error:
        error_id = report_error(error)
        response = JSONResponse({"detail": "The service could not complete this request.", "error_id": error_id}, status_code=500)
    if path.startswith(("/api/auth", "/api/projects")):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/api/health")
def health():
    read_data("counties")
    read_data("parks")
    if auth_required():
        get_store().ready()
    return {"status": "ok", "service": "cartollm", "catalog": "nj"}


@app.get("/api/catalog")
def get_catalog():
    return catalog()


@app.get("/api/workspace/schema")
def workspace_schema():
    return schema()


@app.post("/api/workspace/import")
async def restore_workspace(request: Request):
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_DOCUMENT_BYTES:
            raise HTTPException(413, "Workspace exceeds 1 MiB")
        raw.extend(chunk)
    try:
        return import_workspace(parse_document(bytes(raw)))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.get("/api/data/{dataset}")
def get_data(dataset: str):
    if dataset not in {"counties", "parks", "park_points"}:
        raise HTTPException(404, "Dataset not found")
    return JSONResponse(read_data(dataset), headers={"Cache-Control": "public, max-age=3600"})


@app.post("/api/map")
def make_map(request: MapRequest):
    try:
        return plan(request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.post("/api/chat")
def chat_map(request: ChatRequest, http_request: Request):
    if not AI_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "The agent is busy. Try again shortly.")
    try:
        if request.use_ai and auth_required():
            user = http_request.state.user
            if not user:
                raise HTTPException(401, "Sign in to use AI")
            get_store().consume_ai(user["id"], ai_limit())
        return chat(request)
    except StoreError:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        AI_SLOTS.release()


STATIC = Path(__file__).parent / "static"
app.mount("/assets", StaticFiles(directory=STATIC / "assets", check_dir=False), name="assets")


@app.get("/")
def index():
    if not (STATIC / "index.html").exists():
        return JSONResponse({"detail": "Build the frontend with cd web && npm ci && npm run build, or use the Vite development server."}, status_code=503)
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


def main():
    import uvicorn
    uvicorn.run("autocarto.web.app:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
