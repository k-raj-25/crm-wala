from __future__ import annotations

import datetime as dt

from flask import Blueprint, g, make_response, jsonify
from pydantic import Field

from app.core.auth import attach_cookies, encode_access, protect
from app.core.errors import ApiError, forbidden
from app.core.responses import created, no_content, ok
from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import User, Workspace, WorkspaceMember
from app.models.base import utcnow
from app.schemas.common import Schema, parse, patchify, provided
from app.services import accounts, analytics, audit
from app.services import workspaces as ws_service

bp = Blueprint("workspace", __name__, url_prefix="/api/v1")


class WorkspacePatchIn(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    logo_url: str | None = Field(default=None, max_length=500)
    brand_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    industry: str | None = Field(default=None, max_length=80)
    company_size: str | None = Field(default=None, max_length=40)
    website: str | None = Field(default=None, max_length=300)
    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    locale: str | None = Field(default=None, max_length=10)


@bp.get("/workspace")
@protect("team.read", allow_restricted=True)
def get_workspace():
    return ok(accounts.build_me()["workspace"])


@bp.patch("/workspace")
@protect("settings.manage")
def update_workspace():
    ch = provided(parse(WorkspacePatchIn))
    before = {k: getattr(g.workspace, k) for k in ch}
    for k, v in ch.items():
        if k == "brand_color" or k == "logo_url":
            g.workspace.settings = {**(g.workspace.settings or {}), "branding": {**(g.workspace.settings or {}).get("branding", {}), k: v}}
        if v is not None or k in ("logo_url",):
            setattr(g.workspace, k, v)
    audit.record("workspace.updated", entity_type="workspace", entity_id=g.workspace.id, summary="Workspace settings updated", before=before, after=ch)
    db.session.commit()
    return ok(accounts.build_me()["workspace"])


class OnboardingIn(Schema):
    company_name: str | None = Field(default=None, max_length=160)
    industry: str | None = None
    website: str | None = None
    sales_model: str | None = Field(default=None, pattern="^(b2b|b2c|agency|saas|consulting|real_estate|services|other)$")
    company_size: str | None = None
    goals: list[str] = Field(default_factory=list, max_length=6)
    import_choice: str | None = Field(default=None, pattern="^(scratch|csv|google|integrations)$")
    step: int | None = Field(default=None, ge=0, le=10)
    complete: bool = False


@bp.post("/workspace/onboarding")
@protect(allow_restricted=True)
def onboarding():
    data = parse(OnboardingIn)
    ws = g.workspace
    if data.company_name:
        ws.name = data.company_name
    for f in ("industry", "website", "company_size", "sales_model"):
        v = getattr(data, f)
        if v:
            setattr(ws, f, v)
    if data.goals:
        ws.goals = data.goals
    state = dict(ws.onboarding_state or {})
    if data.step is not None:
        state["step"] = data.step
    if data.import_choice:
        state["import_choice"] = data.import_choice
    ws.onboarding_state = state
    if data.complete and not ws.onboarding_completed_at:
        ws.onboarding_completed_at = utcnow()
        analytics.track("onboarding_completed", {"sales_model": ws.sales_model, "goals": ws.goals})
    db.session.commit()
    return ok(accounts.build_me()["workspace"])


class NewWorkspaceIn(Schema):
    name: str = Field(min_length=1, max_length=160)


@bp.post("/workspaces")
@protect(workspace=False)
def create_workspace():
    data = parse(NewWorkspaceIn)
    owned = db.session.query(Workspace).filter_by(owner_id=g.user.id, deleted_at=None).count()
    if owned >= 5:
        raise ApiError(409, "workspace_limit", "You can own up to 5 workspaces.")
    with bypass_scope():
        ws = ws_service.create_workspace(g.user, data.name)
        audit.record("workspace.created", entity_type="workspace", entity_id=ws.id, workspace_id=ws.id, summary=f"Workspace “{ws.name}” created")
        db.session.commit()
        return created({"workspace_id": str(ws.id), "name": ws.name})


class DeleteIn(Schema):
    confirm_name: str


@bp.delete("/workspace")
@protect(allow_restricted=True)
def delete_workspace():
    if g.member.role.key != "owner":
        raise forbidden("Only the workspace owner can delete it", "owner_only")
    data = parse(DeleteIn)
    if data.confirm_name != g.workspace.name:
        raise ApiError(422, "validation_error", "Type the workspace name exactly to confirm", {"confirm_name": "Doesn't match"})
    g.workspace.deleted_at = utcnow()  # soft delete: data retained for the recovery window, purged by an admin-run job
    audit.record("workspace.deleted", entity_type="workspace", entity_id=g.workspace.id, summary=f"Workspace “{g.workspace.name}” deleted")
    db.session.commit()
    return no_content()
