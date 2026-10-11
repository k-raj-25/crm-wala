"""WhatsApp Business: settings, approved templates, sending from a record or the unit drawer, and Meta's inbound webhook."""
from __future__ import annotations

import uuid

from flask import Blueprint, Response, current_app, g, request
from pydantic import Field

from app.core.auth import protect
from app.core.errors import ApiError, bad_request, not_found
from app.core.responses import created, ok
from app.core.tenant import bypass_scope, set_tenant
from app.extensions import db, limiter
from app.models import Contact, FileAsset, Integration, Lead, Unit, WhatsAppMessage
from app.schemas.common import Schema, parse
from app.services import audit, integrations, whatsapp as svc

bp = Blueprint("whatsapp", __name__, url_prefix="/api/v1/whatsapp")
inbound_bp = Blueprint("whatsapp_inbound", __name__, url_prefix="/api/v1/inbound/whatsapp")


def _feature() -> None:
    if "whatsapp_integration" not in g.features:
        raise ApiError(402, "feature_unavailable", "WhatsApp isn't included in your current plan.", {"feature": "whatsapp_integration"})


def webhook_url(i: Integration) -> str:
    return f"{current_app.config['WEB_ORIGIN']}/api/v1/inbound/whatsapp/{(i.config or {}).get('webhook_token', '')}"


# ---- connect (called from POST /api/v1/integrations/whatsapp/connect) ----------------------------------------------

class ConnectIn(Schema):
    phone_number_id: str | None = Field(default=None, max_length=40)
    waba_id: str | None = Field(default=None, max_length=40)
    access_token: str | None = Field(default=None, max_length=1000)
    app_secret: str | None = Field(default=None, max_length=200)


def connect(i: Integration, body: dict) -> dict:
    d = parse(ConnectIn, body)
    given = {k: (v or "").strip() for k, v in d.model_dump().items()}
    cfg = {**svc.new_webhook_config(), **{k: v for k, v in (i.config or {}).items() if k in ("webhook_token", "verify_token", "media_template")}}
    if any(given.values()):
        missing = {k: "Required" for k, v in given.items() if not v}
        if missing:
            raise ApiError(422, "validation_error", "Fill in all four details from your Meta app, or leave them all empty to try sandbox mode.", missing)
        info = svc.verify_credentials(given["phone_number_id"], given["access_token"])
        integrations.set_creds(i, given)
        i.mode = "live"
        i.account_label = f"{info.get('verified_name') or 'WhatsApp'} · {info.get('display_phone_number') or given['phone_number_id']}"
    else:
        i.credentials_enc, i.mode, i.account_label = None, "sandbox", f"{g.user.email} (sandbox)"
        cfg.pop("media_template", None)
    i.config = cfg
    i.status, i.last_error, i.connected_by = "connected", None, g.user.id
    audit.record("integration.connected", entity_type="integration", entity_id=i.id, summary=f"Connected WhatsApp Business ({i.mode})")
    db.session.commit()
    return {**integrations.public_view("whatsapp", i), "webhook": {"url": webhook_url(i), "verify_token": cfg["verify_token"]}}


# ---- settings ----------------------------------------------------------------------------------------------------

@bp.get("/settings")
@protect("integrations.manage")
def get_settings():
    _feature()
    i = svc.connection(g.workspace.id)
    return ok({"mode": i.mode, "account_label": i.account_label, "webhook": {"url": webhook_url(i), "verify_token": (i.config or {}).get("verify_token")},
               "media_template": (i.config or {}).get("media_template")})


class SettingsIn(Schema):
    media_template: str | None = Field(default=None, max_length=120)  # "name|language", or null to clear


@bp.patch("/settings")
@protect("integrations.manage")
def update_settings():
    _feature()
    i = svc.connection(g.workspace.id)
    d = parse(SettingsIn)
    cfg = dict(i.config or {})
    if d.media_template:
        name, _, lang = d.media_template.partition("|")
        t = next((t for t in svc.list_templates(i) if t["name"] == name and (not lang or t["language"] == lang)), None)
        if t is None or t["header"] not in ("DOCUMENT", "IMAGE"):
            raise ApiError(422, "validation_error", "Pick an approved template with a document or image header.", {"media_template": "Not a media template"})
        cfg["media_template"] = {k: t[k] for k in ("name", "language", "body", "body_params", "header")}
    else:
        cfg.pop("media_template", None)
    i.config = cfg
    db.session.commit()
    return ok({"media_template": cfg.get("media_template")})


@bp.get("/templates")
@protect()
def templates():
    _feature()
    return ok(svc.list_templates(svc.connection(g.workspace.id)))


# ---- messages ----------------------------------------------------------------------------------------------------

def _recipient(lead_id, contact_id) -> tuple[str, Lead | Contact]:
    if bool(lead_id) == bool(contact_id):
        raise bad_request("Choose one lead or contact to message")
    model, etype, ident = (Lead, "lead", lead_id) if lead_id else (Contact, "contact", contact_id)
    e = db.session.query(model).filter(model.id == ident, model.workspace_id == g.workspace.id, model.deleted_at.is_(None)).one_or_none()
    if e is None:
        raise not_found(etype.capitalize())
    return etype, e


@bp.get("/conversation")
@protect("activities.read")
def conversation():
    _feature()
    try:
        etype, e = _recipient(*(uuid.UUID(request.args[k]) if request.args.get(k) else None for k in ("lead_id", "contact_id")))
    except ValueError:
        raise bad_request("Invalid id")
    col = WhatsAppMessage.lead_id if etype == "lead" else WhatsAppMessage.contact_id
    rows = db.session.query(WhatsAppMessage).filter(WhatsAppMessage.workspace_id == g.workspace.id, col == e.id) \
        .order_by(WhatsAppMessage.created_at.desc()).limit(100).all()
    phone = svc.normalize_phone(e.phone)
    i = integrations.get(g.workspace.id, "whatsapp")
    return ok({"phone": phone, "connected": bool(i and i.status in ("connected", "error")), "mode": i.mode if i else None,
               "window_open": bool(phone) and svc.window_open(g.workspace.id, phone), "messages": [m.to_dict() for m in reversed(rows)]})


class TemplateIn(Schema):
    name: str = Field(min_length=1, max_length=120)
    language: str = Field(min_length=2, max_length=15)
    params: list[str] = Field(default_factory=list, max_length=10)


class SendIn(Schema):
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    text: str | None = Field(default=None, max_length=4096)
    template: TemplateIn | None = None
    file_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    caption: str | None = Field(default=None, max_length=1000)


@bp.post("/send")
@protect("emails.create")
@limiter.limit("120 per hour")
def send():
    _feature()
    d = parse(SendIn)
    if sum(bool(x) for x in (d.text, d.template, d.file_id)) != 1 and not (d.template and d.file_id):
        raise bad_request("Send a message, a template or a file")
    i = svc.connection(g.workspace.id)
    etype, e = _recipient(d.lead_id, d.contact_id)
    unit = file = None
    if d.unit_id:
        unit = db.session.query(Unit).filter(Unit.id == d.unit_id, Unit.workspace_id == g.workspace.id, Unit.deleted_at.is_(None)).one_or_none()
        if unit is None:
            raise not_found("Unit")
    if d.file_id:
        file = db.session.query(FileAsset).filter(FileAsset.id == d.file_id, FileAsset.workspace_id == g.workspace.id, FileAsset.deleted_at.is_(None)).one_or_none()
        if file is None:
            raise not_found("File")
        if file.mime_type not in ("application/pdf", "image/jpeg", "image/png"):
            raise ApiError(415, "unsupported_file_type", "WhatsApp can send PDFs and JPG/PNG images. Upload the brochure as a PDF.")
    template = None
    if d.template:
        known = {(t["name"], t["language"]): t for t in svc.list_templates(i)}
        t = known.get((d.template.name, d.template.language))
        if t is None:
            raise ApiError(422, "whatsapp_template_missing", "That template isn't approved for this number or language.")
        if len(d.template.params) != t["body_params"] or any(not p.strip() for p in d.template.params):
            raise ApiError(422, "validation_error", f"Fill in all {t['body_params']} placeholders in the template.", {"params": "Incomplete"})
        if (t["header"] in ("DOCUMENT", "IMAGE")) != (file is not None):
            raise ApiError(422, "validation_error", "This template needs a document or image. Send it from the unit drawer." if file is None
                           else "This template has no document header, so it can't carry a file.", {"file_id": "Mismatch"})
        template = {**t, "params": d.template.params}
    m = svc.send(i, etype, e, text=d.text, template=template, file=file, caption=d.caption, unit=unit)
    db.session.commit()
    return created(m.to_dict())


# ---- Meta webhook ------------------------------------------------------------------------------------------------

def _integration(token: str) -> Integration:
    with bypass_scope():
        i = svc.integration_for_token(token)
    if i is None or i.status == "not_connected":
        raise not_found("Webhook")
    return i


@inbound_bp.get("/<token>")
@limiter.limit("30 per minute")
def verify(token):
    """Meta's one-time subscription check: echo hub.challenge when the verify token matches."""
    i = _integration(token)
    a = request.args
    if a.get("hub.mode") != "subscribe" or a.get("hub.verify_token") != (i.config or {}).get("verify_token"):
        raise ApiError(403, "invalid_verify_token", "Verify token doesn't match.")
    return Response(a.get("hub.challenge", ""), mimetype="text/plain")


@inbound_bp.post("/<token>")
@limiter.limit("600 per minute")
def receive(token):
    i = _integration(token)
    raw = request.get_data(cache=True)
    if i.mode == "live":
        if not svc.valid_signature(i, raw, request.headers.get("X-Hub-Signature-256")):
            raise ApiError(401, "invalid_signature", "Signature check failed.")
    elif current_app.config["ENV"] == "production":
        raise not_found("Webhook")  # sandbox connections never receive real traffic
    ws_id = i.workspace_id
    set_tenant(ws_id)
    from app.models import Workspace

    g.workspace, g.user, g.permissions, g.features, g.member = db.session.get(Workspace, ws_id), None, set(), set(), None
    i = db.session.get(Integration, i.id)
    stats = svc.handle_webhook(i, request.get_json(silent=True) or {})
    db.session.commit()
    return ok(stats)
