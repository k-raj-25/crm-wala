"""Unauthenticated endpoints: lead-capture forms, email open tracking, inbound email."""
from __future__ import annotations

import base64

from flask import Blueprint, Response, g, request
from pydantic import Field
from sqlalchemy import func

from app.core.errors import ApiError, not_found
from app.core.responses import ok
from app.core.tenant import bypass_scope, set_tenant
from app.extensions import db, limiter
from app.models import Activity, Email, Lead, Workspace
from app.models.base import utcnow
from app.schemas.common import Email as EmailStr, Schema, parse
from app.services import activities, analytics, audit, notifications
from app.services.access import compute_access

bp = Blueprint("public", __name__, url_prefix="/api/v1/public")
inbound_bp = Blueprint("inbound", __name__, url_prefix="/api/v1/inbound")
_PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


class FormIn(Schema):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=200)
    job_title: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=5000)
    source: str | None = Field(default=None, max_length=60)
    website_url: str | None = None  # honeypot: real users never fill this


def _workspace_by_token(token: str) -> Workspace:
    ws = db.session.query(Workspace).filter(Workspace.settings["public_form_token"].astext == token, Workspace.deleted_at.is_(None)).first()
    if ws is None:
        raise not_found("Form")
    return ws


@bp.post("/forms/<token>")
@limiter.limit("20 per minute")
def submit_form(token):
    d = parse(FormIn)
    if d.website_url:  # bot
        return ok({"received": True})
    with bypass_scope():
        ws = _workspace_by_token(token)
    if not compute_access(ws).allowed:
        raise ApiError(403, "form_unavailable", "This form is not accepting submissions right now.")
    set_tenant(ws.id)
    g.workspace, g.user, g.permissions, g.features, g.member = ws, None, set(), set(), None
    from app.api.v1.leads import rescore
    from app.services import events

    lead = Lead(workspace_id=ws.id, first_name=d.first_name, last_name=d.last_name, email=d.email, phone=d.phone, company_name=d.company, job_title=d.job_title,
                description=d.message, source=d.source or "website_form", status="new", owner_id=None, tags=["web-form"])
    db.session.add(lead)
    db.session.flush()
    rescore(lead)
    activities.log_activity("created", "Lead captured from website form", workspace_id=ws.id, lead_id=lead.id, body=d.message, user_id=None)
    audit.record("lead.created", entity_type="lead", entity_id=lead.id, workspace_id=ws.id, actor_type="system", actor_label="Website form", summary=f"Lead “{lead.name}” captured from website form")
    analytics.track("lead_created", {"via": "form"}, workspace_id=ws.id)
    notifications.notify(ws.id, notifications.workspace_admins(ws.id), "new_lead", f"New lead from your website: {lead.name}", d.message[:140] if d.message else None, f"/app/leads/{lead.id}")
    events.emit("form.submitted", {"lead_id": str(lead.id), "name": lead.name, "email": lead.email}, workspace_id=ws.id)
    events.emit("lead.created", {"lead_id": str(lead.id), "name": lead.name, "email": lead.email}, workspace_id=ws.id)
    db.session.commit()
    return ok({"received": True})


@bp.get("/t/<tid>.gif")
@limiter.limit("120 per minute")
def track_open(tid):
    with bypass_scope():
        e = db.session.query(Email).filter_by(tracking_id=tid).one_or_none()
        if e is not None:
            e.opens += 1
            e.first_opened_at = e.first_opened_at or utcnow()
            db.session.commit()
    resp = Response(_PIXEL, mimetype="image/gif")
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


class InboundIn(Schema):
    from_address: EmailStr = Field(alias="from")
    to: list[EmailStr] = Field(default_factory=list)
    subject: str = Field(default="(no subject)", max_length=500)
    text: str = Field(default="", max_length=100000)
    message_id: str | None = Field(default=None, max_length=300)


@inbound_bp.post("/email/<token>")
@limiter.limit("60 per minute")
def inbound_email(token):
    """Webhook target for inbound-parse providers (SendGrid/Postmark/Mailgun/Zapier). Matches the sender to a contact or lead."""
    d = parse(InboundIn)
    with bypass_scope():
        ws = _workspace_by_token(token)
    set_tenant(ws.id)
    if d.message_id and db.session.query(Email.id).filter_by(workspace_id=ws.id, provider_message_id=d.message_id).first():
        return ok({"duplicate": True})
    from app.models import Contact

    rel: dict = {}
    c = db.session.query(Contact).filter(Contact.workspace_id == ws.id, Contact.deleted_at.is_(None), func.lower(Contact.email) == d.from_address).first()
    if c:
        rel = {"contact_id": c.id, "company_id": c.company_id}
    else:
        l = db.session.query(Lead).filter(Lead.workspace_id == ws.id, Lead.deleted_at.is_(None), func.lower(Lead.email) == d.from_address).first()
        if l:
            rel = {"lead_id": l.id}
    e = Email(workspace_id=ws.id, direction="inbound", status="received", subject=d.subject, body=d.text, from_address=d.from_address, to_addresses=d.to, sent_at=utcnow(),
              provider="inbound-webhook", provider_message_id=d.message_id, **rel)
    db.session.add(e)
    if rel:
        activities.log_activity("email", f"Email received: {d.subject}", workspace_id=ws.id, body=d.text[:500], user_id=None, data={"email_id": str(e.id)}, **rel)
    db.session.commit()
    return ok({"matched": bool(rel)})
