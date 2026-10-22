"""Calling through the company number: connect a provider, routing settings, click-to-call, live calls and hand-overs,
and the provider's webhooks (see services/calling.py)."""
from __future__ import annotations

import uuid

from flask import Blueprint, g, request
from pydantic import Field

from app.core.auth import protect
from app.core.errors import ApiError, bad_request, not_found
from app.core.responses import created, ok
from app.core.tenant import bypass_scope, set_tenant
from app.extensions import db, limiter
from app.models import Contact, Integration, Lead, User, WorkspaceMember
from app.schemas.common import Schema, parse
from app.services import audit, calling as svc, integrations
from app.services.telephony import adapter

bp = Blueprint("calling", __name__, url_prefix="/api/v1/calling")
inbound_bp = Blueprint("calling_inbound", __name__, url_prefix="/api/v1/inbound/calls")


def _hooks(i: Integration) -> list[dict]:
    p = adapter(i.provider)
    return [{"key": k, "label": label, "url": svc.webhook_url(i, k)} for k, label in p.hooks.items() if k != "status"]


# ---- connect (called from POST /api/v1/integrations/<provider>/connect) ---------------------------------------------

def connect(i: Integration, body: dict) -> dict:
    """Verify the firm's own provider account and store it encrypted. On a reconnect, blank fields keep the saved values."""
    p = adapter(i.provider)
    old = integrations.get_creds(i) if i.credentials_enc else {}
    creds = {f["key"]: (str(body.get(f["key"]) or "")).strip() or old.get(f["key"], "") for f in p.fields}
    missing = {f["key"]: "Required" for f in p.fields if not f.get("optional") and not creds[f["key"]]}
    if missing:
        raise ApiError(422, "validation_error", f"Fill in the details from your {p.name} account.", missing)
    other = svc.find_connection(g.workspace.id)
    if other is not None and other.id != i.id:
        raise ApiError(409, "calling_already_connected", f"Disconnect {integrations.CATALOG[other.provider]['name']} first: one calling provider at a time.")
    label = p.verify(creds)
    integrations.set_creds(i, creds)
    cfg = dict(i.config or {})
    cfg.setdefault("webhook_token", svc.new_webhook_config()["webhook_token"])
    i.config, i.mode, i.account_label = cfg, "live", label
    i.status, i.last_error, i.connected_by = "connected", None, g.user.id
    audit.record("integration.connected", entity_type="integration", entity_id=i.id, summary=f"Connected calling ({label})")
    db.session.commit()
    return {**integrations.public_view(i.provider, i), "calling": _settings(i)}


def _settings(i: Integration) -> dict:
    p = adapter(i.provider)
    creds = integrations.get_creds(i)
    return {"provider": i.provider, "account_label": i.account_label, "hooks": _hooks(i), "routing": svc.routing(i),
            "has_flow": bool(creds.get("flow_app_id")), "fields": [{**f, "value": None if f.get("secret") else creds.get(f["key"])} for f in p.fields]}


# ---- status & settings -------------------------------------------------------------------------------------------

@bp.get("/status")
@protect()
def status():
    """What the browser needs to decide between "Call via company number" and the old call logger."""
    i = svc.find_connection(g.workspace.id)
    return ok({"enabled": i is not None, "provider": i.provider if i else None, "my_phone_set": bool(svc.member_phone(g.workspace.id, g.user.id)),
               "can_transfer_inbound": bool(i) and adapter(i.provider).can_transfer(svc.creds_for(i), "inbound"),
               "can_transfer_outbound": bool(i) and adapter(i.provider).can_transfer(svc.creds_for(i), "outbound")})


@bp.get("/settings")
@protect("integrations.manage")
def get_settings():
    i, _ = svc.connection(g.workspace.id)
    return ok(_settings(i))


class RoutingIn(Schema):
    inbound: str | None = Field(default=None, pattern="^(lead_owner|fallback)$")
    fallback_user_id: uuid.UUID | None = None
    ring_fallback_too: bool | None = None
    create_leads: bool | None = None
    record: bool | None = None
    ring_seconds: int | None = Field(default=None, ge=10, le=60)
    client_first: bool | None = None
    greeting: bool | None = None


@bp.patch("/settings")
@protect("integrations.manage")
def update_settings():
    i, _ = svc.connection(g.workspace.id)
    body = request.get_json(silent=True) or {}
    d = parse(RoutingIn, body)
    r = svc.routing(i)
    for k, v in d.model_dump().items():
        if k in body:
            r[k] = str(v) if isinstance(v, uuid.UUID) else v
    if r.get("fallback_user_id"):
        fid = uuid.UUID(str(r["fallback_user_id"]))
        if not db.session.query(WorkspaceMember.id).filter_by(workspace_id=g.workspace.id, user_id=fid, status="active").first():
            raise ApiError(422, "validation_error", "Pick an active team member.", {"fallback_user_id": "Not a member"})
        if not svc.member_phone(g.workspace.id, fid):
            raise ApiError(422, "validation_error", "That person has no mobile number on their profile, so calls can't ring them.", {"fallback_user_id": "No phone"})
    if r["client_first"] and not integrations.get_creds(i).get("flow_app_id"):
        raise ApiError(422, "validation_error", "Add the call flow app ID first (reconnect and fill it in).", {"client_first": "Needs the call flow"})
    i.config = {**(i.config or {}), "routing": r}
    audit.record("calling.settings_updated", entity_type="integration", entity_id=i.id, summary="Updated calling settings")
    db.session.commit()
    return ok(_settings(i))


# ---- calls -------------------------------------------------------------------------------------------------------

class CallIn(Schema):
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None


@bp.post("/call")
@protect("calls.place")
@limiter.limit("60 per hour")
def place():
    d = parse(CallIn)
    if bool(d.lead_id) == bool(d.contact_id):
        raise bad_request("Choose one lead or client to call")
    model, etype, ident = (Lead, "lead", d.lead_id) if d.lead_id else (Contact, "contact", d.contact_id)
    e = db.session.query(model).filter(model.id == ident, model.workspace_id == g.workspace.id, model.deleted_at.is_(None)).one_or_none()
    if e is None:
        raise not_found(etype.capitalize())
    call = svc.place_call(etype, e)
    db.session.commit()
    return created(svc.serialize_live(call))


@bp.get("/active")
@protect()
def active():
    rows = svc.active_calls(g.workspace.id, g.user.id)
    db.session.commit()  # stale calls are closed on the way
    return ok([svc.serialize_live(c) for c in rows])


@bp.get("/calls/<uuid:cid>/transfer-targets")
@protect("calls.place")
def targets(cid):
    svc.live_call(g.workspace.id, cid)
    return ok({"any": svc.can_transfer_any(g.permissions), "targets": svc.transfer_targets(g.workspace.id, g.user.id, g.permissions)})


class TransferIn(Schema):
    to_user_id: uuid.UUID


@bp.post("/calls/<uuid:cid>/transfer")
@protect("calls.place")
def transfer(cid):
    d = parse(TransferIn)
    call = svc.live_call(g.workspace.id, cid)
    out = svc.request_transfer(call, d.to_user_id)
    db.session.commit()
    return ok({**svc.serialize_live(call), **out})


@bp.delete("/calls/<uuid:cid>/transfer")
@protect("calls.place")
def cancel(cid):
    call = svc.live_call(g.workspace.id, cid)
    svc.cancel_transfer(call)
    db.session.commit()
    return ok(svc.serialize_live(call))


# ---- team: who reports to whom (for hand-overs) -----------------------------------------------------------------

class ReportsIn(Schema):
    reports_to: uuid.UUID | None = None


@bp.patch("/members/<uuid:mid>/manager")
@protect("team.manage")
def set_manager(mid):
    m = db.session.query(WorkspaceMember).filter_by(id=mid, workspace_id=g.workspace.id).one_or_none()
    if m is None:
        raise not_found("Member")
    d = parse(ReportsIn)
    if d.reports_to:
        if d.reports_to == m.user_id:
            raise ApiError(422, "validation_error", "Someone can't report to themselves.", {"reports_to": "Same person"})
        if not db.session.query(WorkspaceMember.id).filter_by(workspace_id=g.workspace.id, user_id=d.reports_to).first():
            raise ApiError(422, "validation_error", "Pick a member of this workspace.", {"reports_to": "Not a member"})
    m.reports_to = d.reports_to
    who = db.session.get(User, d.reports_to).name if d.reports_to else "nobody"
    audit.record("team.member_updated", entity_type="user", entity_id=m.user_id, summary=f"{m.user.name} now reports to {who}")
    db.session.commit()
    return ok({"id": str(m.id), "reports_to": str(m.reports_to) if m.reports_to else None})


# ---- provider webhooks -------------------------------------------------------------------------------------------

@inbound_bp.route("/<token>/<hook>", methods=["GET", "POST"])
@limiter.limit("600 per minute")
def webhook(token, hook):
    with bypass_scope():
        i = svc.integration_for_token(token)
    if i is None or i.status == "not_connected":
        raise not_found("Webhook")
    p = adapter(i.provider)
    if hook not in p.hooks:
        raise not_found("Webhook")
    ws_id = i.workspace_id
    set_tenant(ws_id)
    from app.models import Workspace

    g.workspace, g.user, g.permissions, g.features, g.member = db.session.get(Workspace, ws_id), None, set(), set(), None
    i = db.session.get(Integration, i.id)
    leg = p.parse(hook, request)
    if leg is None:
        raise bad_request("Missing call id")
    if hook == "connect":
        dial = svc.handle_connect(i, leg)
        db.session.commit()
        if dial is None:
            raise ApiError(404, "nobody_to_ring", "Nobody to ring for this call.")
        return p.dial_response(dial)
    if hook == "handover":
        go_on = svc.handle_handover(i, leg)
        db.session.commit()
        return p.branch_response(go_on)
    svc.handle_status(i, leg)
    db.session.commit()
    return ok({"received": True})
