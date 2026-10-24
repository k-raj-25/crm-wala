"""Sharing a society's public page with a client, and the page's own no-login endpoints."""
from __future__ import annotations

import datetime as dt
import uuid
from types import SimpleNamespace
from typing import Literal
from urllib.parse import quote

from flask import Blueprint, g, redirect, request, send_file
from pydantic import Field

from app.api.v1.comparisons import _disposition, _phone_digits
from app.core.auth import protect, require
from app.core.crud import ensure_ref
from app.core.errors import ApiError, not_found
from app.core.responses import ok
from app.core.tenant import bypass_scope, set_tenant
from app.extensions import db, limiter
from app.models import Activity, Contact, FileAsset, Lead, Project, Workspace
from app.models.base import utcnow
from app.schemas.common import Email, Schema, parse
from app.services import activities, audit, mailbox, notifications, storage
from app.services import society_page as page
from app.services.access import compute_access
from app.services.usage import check_limit

bp = Blueprint("society_share", __name__, url_prefix="/api/v1/projects")
public_bp = Blueprint("public_societies", __name__, url_prefix="/api/v1/public/societies")

OPEN_NOTICE_EVERY = dt.timedelta(hours=6)  # one "opened your link" note per client per few hours, however often they look


class ShareIn(Schema):
    channel: Literal["link", "whatsapp", "email"]
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    hide_prices: bool = False
    client_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    to: list[Email] = Field(default_factory=list, max_length=10)
    subject: str | None = Field(default=None, max_length=300)
    message: str | None = Field(default=None, max_length=5000)


@bp.post("/<uuid:pid>/share")
@protect("projects.read")
@limiter.limit("120 per hour")
def share(pid):
    """Makes the society's public link. With a lead or client picked it is filed on their timeline; WhatsApp hands back a
    wa.me link with the message, email sends it from the employee's mailbox."""
    d = parse(ShareIn)
    p = db.session.query(Project).filter(Project.id == pid, Project.workspace_id == g.workspace.id, Project.deleted_at.is_(None)).one_or_none()
    if p is None:
        raise not_found("Project")
    rel: dict = {}
    if d.lead_id:
        ensure_ref(Lead, d.lead_id, "lead_id")
        rel["lead_id"] = d.lead_id
    elif d.contact_id:
        ensure_ref(Contact, d.contact_id, "contact_id")
        rel["contact_id"] = d.contact_id
        c = db.session.get(Contact, d.contact_id)
        if c.company_id:
            rel["company_id"] = c.company_id
    if d.channel == "email":
        require("emails.create")
        if not d.to:
            raise ApiError(422, "validation_error", "Add the client's email address", {"to": "Add an email address"})
        if not g.user.email_verified_at:
            raise ApiError(403, "email_not_verified", "Verify your email address to send emails. Check your inbox for the link, or request a new one.")
        check_limit(g.workspace, "emails_month", len(d.to))

    token = page.make_token(page.Link(project_id=p.id, sharer_id=g.user.id, flags=page.HIDE_PRICES if d.hide_prices else 0,
                                      lead_id=rel.get("lead_id"), contact_id=rel.get("contact_id")))
    url = page.page_url(token)
    rec = db.session.get(Lead, rel["lead_id"]) if rel.get("lead_id") else db.session.get(Contact, rel["contact_id"]) if rel.get("contact_id") else None
    first = (d.client_name or (rec.first_name if rec else "") or "").strip().split(" ")[0] or "there"
    out = {"channel": d.channel, "url": url}

    if d.channel == "email":
        subject = d.subject or f"{p.name}: photos, floor plans and brochure"
        body = d.message or f"Hi {{{{first_name}}}},\n\nHere is everything about {p.name}: photos, layouts, floor plans and the brochure, all on one page.\n\n{{{{link}}}}\n\nHappy to arrange a site visit whenever suits you.\n\n{{{{sender_name}}}}"
        ctx = {"first_name": first, "sender_name": g.user.name, "link": url}
        body = mailbox.merge_fields(body, ctx)
        if url not in body:
            body = f"{body.rstrip()}\n\n{url}"
        email = mailbox.send_crm_email(g.user, to=d.to, cc=[], subject=mailbox.merge_fields(subject, ctx), body=body, track=True, related=rel, attachment_file_ids=[])
        if email.status == "failed":
            db.session.rollback()
            raise ApiError(502, "delivery_failed", f"The email couldn't be delivered: {email.error or 'unknown error'}")
        out.update(status=email.status, email_id=str(email.id))
    elif d.channel == "whatsapp":
        text = (d.message or f"Hi {first}, here are the details of {p.name}: photos, layouts, floor plans and the brochure.").replace("{{first_name}}", first).strip()
        text = text if url in text else f"{text}\n\n{url}"
        phone = _phone_digits(d.phone)
        out.update(text=text, whatsapp_url=f"https://wa.me/{phone}?text={quote(text)}" if phone else f"https://wa.me/?text={quote(text)}")

    if rel and d.channel != "email":  # a sent email files itself on the timeline
        title = f"{p.name} society page sent on WhatsApp" if d.channel == "whatsapp" else f"Link to the {p.name} society page made for them"
        activities.log_activity("whatsapp" if d.channel == "whatsapp" else "note", title, body=url, data={"project_id": str(p.id), "channel": d.channel}, **rel)
        if d.channel == "whatsapp":
            mailbox.touch_contacted(SimpleNamespace(lead_id=rel.get("lead_id"), contact_id=rel.get("contact_id")), utcnow())
    audit.record("society_page.shared", entity_type="project", entity_id=p.id, summary=f"Shared the {p.name} society page ({d.channel})")
    db.session.commit()
    return ok(out)


# ---- public, no login ------------------------------------------------------------------------------------------------

def _resolve(token: str) -> tuple[page.Link, Project]:
    """The link and its project, or a plain 404 for a bad token, a deleted project or a workspace that's not active."""
    link = page.read_token(token)
    if link is None:
        raise not_found("Page")
    with bypass_scope():
        p = db.session.query(Project).filter(Project.id == link.project_id, Project.deleted_at.is_(None)).one_or_none()
        ws = db.session.get(Workspace, p.workspace_id) if p else None
    if p is None or ws is None or ws.deleted_at is not None or not compute_access(ws).allowed:
        raise not_found("Page")
    set_tenant(ws.id)
    return link, p


@public_bp.get("/<token>")
@limiter.limit("120 per minute")
def public_page(token):
    link, p = _resolve(token)
    resp = ok(page.build(p, link, token))
    resp.headers["Cache-Control"] = "private, max-age=60"
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


@public_bp.get("/<token>/files/<uuid:fid>")
@limiter.limit("240 per minute")
def public_file(token, fid):
    """A photo, floor plan or brochure of this society. Any other file, even in the same workspace, is a 404."""
    _, p = _resolve(token)
    f = db.session.query(FileAsset).filter(FileAsset.id == fid, FileAsset.project_id == p.id, FileAsset.unit_id.is_(None), FileAsset.deleted_at.is_(None),
                                           FileAsset.doc_kind.in_(page.PUBLIC_KINDS)).one_or_none()
    if f is None:
        raise not_found("File")
    download = request.args.get("download") == "1"
    st = storage.get_storage()
    if isinstance(st, storage.LocalStorage):
        path = st.open(f.storage_key)
        if not path.exists():
            raise not_found("File")
        resp = send_file(path, mimetype=f.mime_type or "application/octet-stream", as_attachment=download, download_name=f.filename, max_age=3600)
        if download:
            resp.headers["Content-Disposition"] = _disposition(f.filename)
        resp.headers["Content-Security-Policy"] = "sandbox"
        resp.headers["X-Robots-Tag"] = "noindex"
        return resp
    return redirect(st.signed_url(f.storage_key, f.filename, expires=3600))


@public_bp.post("/<token>/opened")
@limiter.limit("30 per minute")
def opened(token):
    """Sent by the page itself once it's on screen (link-preview bots don't run it). When the link was made for a lead or
    client, the employee gets a note that they're looking, at most once every few hours."""
    link, p = _resolve(token)
    rec = page.recipient(link)
    if rec is None:
        return ok({"noted": False})
    rel = {"lead_id": rec.id} if isinstance(rec, Lead) else {"contact_id": rec.id}
    since = utcnow() - OPEN_NOTICE_EVERY
    recent = db.session.query(Activity.id).filter(Activity.workspace_id == p.workspace_id, Activity.created_at >= since,
                                                  Activity.data["society_page_opened"].astext == str(p.id),
                                                  *(getattr(Activity, k) == v for k, v in rel.items())).first()
    if recent:
        return ok({"noted": False})
    name = rec.name
    activities.log_activity("note", f"{name} opened the {p.name} society page", workspace_id=p.workspace_id, user_id=None, touch=False,
                            data={"society_page_opened": str(p.id)}, **rel)
    who = rec.owner_id if getattr(rec, "owner_id", None) else link.sharer_id
    link_to = f"/app/leads/{rec.id}" if isinstance(rec, Lead) else f"/app/contacts/{rec.id}"
    notifications.notify(p.workspace_id, {link.sharer_id, who}, "client_viewing", f"{name} is looking at {p.name}",
                         "They just opened the society page you shared. A good moment to call.", link_to)
    db.session.commit()
    return ok({"noted": True})
