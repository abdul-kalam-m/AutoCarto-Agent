"""Cookie sessions, invitation-only enrollment, and owned project APIs."""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from autocarto.traces import MAX_DOCUMENT_BYTES, parse_document
from .store import ai_limit, auth_required, get_store, production
from .workspace import import_workspace

router = APIRouter(prefix="/api")
COOKIE = "cartollm_session"


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=12, max_length=128)
    invitation: str | None = Field(default=None, max_length=100)


class SaveProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    revision: int = Field(default=0, ge=0)
    workspace: dict


def owned_user(request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Sign in to save or open projects")
    return user


def set_session(response, token):
    response.set_cookie(COOKIE, token, httponly=True, secure=production(), samesite="strict", max_age=7 * 86400, path="/")
    response.headers["Cache-Control"] = "no-store"


@router.get("/auth/me")
def me(request: Request):
    user = getattr(request.state, "user", None)
    return {"auth_required": auth_required(), "user": user, "quota": get_store().quota(user["id"], ai_limit()) if user else None}


@router.post("/auth/login")
def login(body: Credentials, response: Response):
    token = get_store().login(body.email, body.password)
    set_session(response, token)
    return {"user": get_store().user(token)}


@router.post("/auth/register")
def register(body: Credentials, response: Response):
    if not body.invitation:
        raise HTTPException(400, "A private-beta invitation is required")
    token = get_store().register(body.email, body.password, body.invitation)
    set_session(response, token)
    return {"user": get_store().user(token)}


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    get_store().logout(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/", secure=production(), httponly=True, samesite="strict")
    return {"ok": True}


@router.get("/projects")
def list_projects(request: Request):
    return get_store().list_projects(owned_user(request)["id"])


@router.get("/projects/{project_id}")
def open_project(project_id: str, request: Request):
    project = get_store().project(owned_user(request)["id"], project_id)
    try:
        project["workspace"] = import_workspace(project["workspace"])
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return project


def save_project(body, request, project_id=None):
    import json
    user = owned_user(request)
    try:
        raw = json.dumps(body.workspace, allow_nan=False).encode()
        document = import_workspace(parse_document(raw))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return get_store().save(user["id"], project_id, body.name.strip() or "Untitled map", document, body.revision)


@router.post("/projects")
def create_project(body: SaveProject, request: Request):
    return save_project(body, request)


@router.put("/projects/{project_id}")
def update_project(project_id: str, body: SaveProject, request: Request):
    return save_project(body, request, project_id)
