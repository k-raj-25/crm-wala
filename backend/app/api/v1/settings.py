"""Workspace configuration: tags, custom fields, lead statuses, saved views, user preferences, notification prefs."""
from __future__ import annotations

import re
import uuid
from typing import Literal

from flask import Blueprint, g
from pydantic import Field
from sqlalchemy import or_

from app.core.auth import protect
from app.core.errors import ApiError, conflict, not_found
from app.core.responses import created, no_content, ok
from app.extensions import db
from app.models import CustomFieldDef, Lead, SavedView, Tag
from app.schemas.common import Schema, parse, provided
from app.services import audit
from app.services.custom_fields import TYPES
from app.services.notifications import DEFAULT_PREFS, NOTIFICATION_TYPES, prefs_for

bp = Blueprint("settings", __name__, url_prefix="/api/v1")


# ---- tags -------------------------------------------------------------------------------

class TagIn(Schema):
    name: str = Field(min_length=1, max_length=40)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


@bp.get("/tags")
@protect("leads.read")
def list_tags():
    return ok([t.to_dict() for t in db.session.query(Tag).filter_by(workspace_id=g.workspace.id).order_by(Tag.name)])


@bp.post("/tags")
@protect("settings.manage")
def create_tag():
    d = parse(TagIn)
    if db.session.query(Tag).filter_by(workspace_id=g.workspace.id, name=d.name).first():
        raise conflict("A tag with that name already exists")
    t = Tag(workspace_id=g.workspace.id, name=d.name, color=d.color or "#6366f1")
    db.session.add(t)
    db.session.commit()
    return created(t.to_dict())


@bp.patch("/tags/<uuid:tid>")
@protect("settings.manage")
def update_tag(tid):
    t = db.session.query(Tag).filter_by(id=tid, workspace_id=g.workspace.id).one_or_none()
    if t is None:
        raise not_found("Tag")
    ch = provided(parse(TagIn))
    if ch.get("name") and ch["name"] != t.name:
        # Rename everywhere the tag is used.
        from sqlalchemy import text

        for table in ("leads", "contacts", "companies", "deals"):
            db.session.execute(text(f"UPDATE {table} SET tags = array_replace(tags, :old, :new) WHERE workspace_id = :w AND :old = ANY(tags)"),
                               {"old": t.name, "new": ch["name"], "w": g.workspace.id})
        t.name = ch["name"]
    if ch.get("color"):
        t.color = ch["color"]
    db.session.commit()
    return ok(t.to_dict())


@bp.delete("/tags/<uuid:tid>")
@protect("settings.manage")
def delete_tag(tid):
    t = db.session.query(Tag).filter_by(id=tid, workspace_id=g.workspace.id).one_or_none()
    if t is None:
        raise not_found("Tag")
    from sqlalchemy import text

    for table in ("leads", "contacts", "companies", "deals"):
        db.session.execute(text(f"UPDATE {table} SET tags = array_remove(tags, :n) WHERE workspace_id = :w"), {"n": t.name, "w": g.workspace.id})
    db.session.delete(t)
    db.session.commit()
    return no_content()


# ---- custom fields ----------------------------------------------------------------------

class CustomFieldIn(Schema):
    entity_type: Literal["lead", "contact", "company", "deal"]
    label: str = Field(min_length=1, max_length=100)
    field_type: Literal["text", "number", "currency", "date", "dropdown", "multi_select", "checkbox", "url", "email", "phone"]
    options: list[str] = Field(default_factory=list, max_length=50)
    required: bool = False


@bp.get("/custom-fields")
@protect("leads.read")
def list_custom_fields():
    rows = db.session.query(CustomFieldDef).filter_by(workspace_id=g.workspace.id).order_by(CustomFieldDef.entity_type, CustomFieldDef.position).all()
    return ok([r.to_dict() for r in rows])


@bp.post("/custom-fields")
@protect("settings.manage", feature="custom_fields")
def create_custom_field():
    d = parse(CustomFieldIn)
    if d.field_type in ("dropdown", "multi_select") and not d.options:
        raise ApiError(422, "validation_error", "Add at least one option", {"options": "Required"})
    key = re.sub(r"[^a-z0-9]+", "_", d.label.lower()).strip("_")[:50] or "field"
    base, n = key, 1
    while db.session.query(CustomFieldDef).filter_by(workspace_id=g.workspace.id, entity_type=d.entity_type, key=key).first():
        n += 1
        key = f"{base}_{n}"
    pos = db.session.query(CustomFieldDef).filter_by(workspace_id=g.workspace.id, entity_type=d.entity_type).count()
    f = CustomFieldDef(workspace_id=g.workspace.id, key=key, position=pos, **d.model_dump())
    db.session.add(f)
    audit.record("custom_field.created", entity_type="custom_field", entity_id=f.id, summary=f"Created custom field “{f.label}” on {f.entity_type}s")
    db.session.commit()
    return created(f.to_dict())


@bp.patch("/custom-fields/<uuid:fid>")
@protect("settings.manage", feature="custom_fields")
def update_custom_field(fid):
    f = db.session.query(CustomFieldDef).filter_by(id=fid, workspace_id=g.workspace.id).one_or_none()
    if f is None:
        raise not_found("Custom field")

    class In(Schema):
        label: str | None = Field(default=None, max_length=100)
        options: list[str] | None = None
        required: bool | None = None

    ch = provided(parse(In))
    for k, v in ch.items():
        if v is not None:
            setattr(f, k, v)
    db.session.commit()
    return ok(f.to_dict())


@bp.delete("/custom-fields/<uuid:fid>")
@protect("settings.manage", feature="custom_fields")
def delete_custom_field(fid):
    f = db.session.query(CustomFieldDef).filter_by(id=fid, workspace_id=g.workspace.id).one_or_none()
    if f is None:
        raise not_found("Custom field")
    audit.record("custom_field.deleted", entity_type="custom_field", entity_id=f.id, summary=f"Deleted custom field “{f.label}”")
    db.session.delete(f)  # values remain in records' JSON but are no longer shown/validated
    db.session.commit()
    return no_content()


# ---- lead statuses ----------------------------------------------------------------------

class StatusItem(Schema):
    key: str = Field(pattern=r"^[a-z0-9_]{2,30}$")
    label: str = Field(min_length=1, max_length=40)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")


class StatusesIn(Schema):
    statuses: list[StatusItem] = Field(min_length=2, max_length=20)


@bp.put("/settings/lead-statuses")
@protect("settings.manage")
def put_lead_statuses():
    d = parse(StatusesIn)
    keys = [s.key for s in d.statuses]
    if len(set(keys)) != len(keys):
        raise ApiError(422, "validation_error", "Status keys must be unique", {"statuses": "Duplicate keys"})
    if not {"new", "converted", "lost"} <= set(keys):
        raise ApiError(422, "validation_error", "“new”, “converted” and “lost” statuses are required", {"statuses": "Required statuses missing"})
    in_use = {r[0] for r in db.session.query(Lead.status).filter(Lead.workspace_id == g.workspace.id, Lead.deleted_at.is_(None)).distinct()}
    removed = in_use - set(keys)
    if removed:
        raise conflict(f"Leads still use: {', '.join(sorted(removed))}. Move them to another status first.", "status_in_use")
    g.workspace.settings = {**(g.workspace.settings or {}), "lead_statuses": [s.model_dump() for s in d.statuses]}
    audit.record("workspace.lead_statuses_updated", entity_type="workspace", entity_id=g.workspace.id, summary="Lead statuses updated")
    db.session.commit()
    return ok(g.workspace.settings["lead_statuses"])


# ---- saved views ------------------------------------------------------------------------

class ViewIn(Schema):
    entity_type: Literal["lead", "contact", "company", "deal", "task"]
    name: str = Field(min_length=1, max_length=80)
    filters: dict = Field(default_factory=dict)
    sort: str | None = Field(default=None, max_length=60)
    columns: list[str] = Field(default_factory=list, max_length=30)
    shared: bool = False


@bp.get("/views")
@protect("leads.read")
def list_views():
    from flask import request

    q = db.session.query(SavedView).filter(SavedView.workspace_id == g.workspace.id, or_(SavedView.owner_id == g.user.id, SavedView.shared.is_(True)))
    if request.args.get("entity_type"):
        q = q.filter(SavedView.entity_type == request.args["entity_type"])
    return ok([v.to_dict() for v in q.order_by(SavedView.created_at)])


@bp.post("/views")
@protect("leads.read")
def create_view():
    d = parse(ViewIn)
    v = SavedView(workspace_id=g.workspace.id, owner_id=g.user.id, **d.model_dump())
    db.session.add(v)
    db.session.commit()
    return created(v.to_dict())


@bp.delete("/views/<uuid:vid>")
@protect("leads.read")
def delete_view(vid):
    v = db.session.query(SavedView).filter_by(id=vid, workspace_id=g.workspace.id).one_or_none()
    if v is None or (v.owner_id != g.user.id and "settings.manage" not in g.permissions and "*" not in g.permissions):
        raise not_found("View")
    db.session.delete(v)
    db.session.commit()
    return no_content()


# ---- user preferences & notification preferences ----------------------------------------

class PrefsIn(Schema):
    theme: Literal["light", "dark", "system"] | None = None
    date_format: Literal["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"] | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=10)
    default_pipeline_id: uuid.UUID | None = None
    dashboard_widgets: list[str] | None = None
    sidebar_collapsed: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    job_role: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    avatar_url: str | None = Field(default=None, max_length=500)


@bp.patch("/me/preferences")
@protect(workspace=False)
def update_preferences():
    ch = provided(parse(PrefsIn))
    for k in ("name", "job_role", "phone", "avatar_url"):
        if k in ch and ch[k] is not None:
            setattr(g.user, k, ch.pop(k))
    prefs = dict(g.user.preferences or {})
    for k, v in ch.items():
        prefs[k] = str(v) if isinstance(v, uuid.UUID) else v
    g.user.preferences = prefs
    db.session.commit()
    from app.services.accounts import build_me

    return ok(build_me())


@bp.get("/me/notification-preferences")
@protect()
def get_notification_prefs():
    return ok([{"type": t, "label": label, **prefs_for(g.member, t)} for t, label in NOTIFICATION_TYPES.items()])


class NotifPrefsIn(Schema):
    prefs: dict[str, dict[str, bool]]


@bp.put("/me/notification-preferences")
@protect()
def put_notification_prefs():
    d = parse(NotifPrefsIn)
    clean = {t: {"in_app": bool(v.get("in_app", True)), "email": bool(v.get("email", False))} for t, v in d.prefs.items() if t in NOTIFICATION_TYPES}
    g.member.notification_prefs = {**(g.member.notification_prefs or {}), **clean}
    db.session.commit()
    return ok([{"type": t, "label": label, **prefs_for(g.member, t)} for t, label in NOTIFICATION_TYPES.items()])
