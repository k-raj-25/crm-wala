"""Visit recap: the rep builds it when a site visit ends and sends it on WhatsApp in one tap; the family opens it without logging in."""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from urllib.parse import quote

from flask import Blueprint, g, redirect, request, send_file
from pydantic import Field

from app.core.auth import protect
from app.core.crud import ensure_ref
from app.core.errors import ApiError, bad_request, conflict, not_found
from app.core.responses import created, ok
from app.core.tenant import bypass_scope, set_tenant
from app.extensions import db, limiter
from app.models import (
    Contact,
    Deal,
    FileAsset,
    Lead,
    Meeting,
    Unit,
    VisitRecap,
    Workspace,
)
from app.models.base import utcnow
from app.schemas.common import Schema, parse
from app.services import activities, audit, integrations, mailbox, privacy, storage
from app.services import visit_recaps as svc
from app.services import whatsapp as wa

bp = Blueprint("visit_recaps", __name__, url_prefix="/api/v1/visit-recaps")
public_bp = Blueprint("public_visit_recaps", __name__, url_prefix="/api/v1/public/recaps")


class RecapIn(Schema):
    meeting_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    unit_ids: list[uuid.UUID] | None = Field(default=None, max_length=svc.MAX_FLATS * 2)
    photo_ids: list[uuid.UUID] | None = Field(default=None, max_length=svc.MAX_PHOTOS * 2)
    message: str | None = Field(default=None, max_length=2000)


class RecapPatch(Schema):
    unit_ids: list[uuid.UUID] | None = Field(default=None, max_length=svc.MAX_FLATS * 2)
    photo_ids: list[uuid.UUID] | None = Field(default=None, max_length=svc.MAX_PHOTOS * 2)
    message: str | None = Field(default=None, max_length=2000)


def _get(rid) -> VisitRecap:
    r = db.session.query(VisitRecap).filter(VisitRecap.id == rid, VisitRecap.workspace_id == g.workspace.id).one_or_none()
    if r is None:
        raise not_found("Visit recap")
    return r


@bp.get("")
@protect("meetings.read")
def list_recaps():
    q = db.session.query(VisitRecap).filter(VisitRecap.workspace_id == g.workspace.id)
    filtered = False
    for k in ("meeting_id", "lead_id", "contact_id", "deal_id"):
        if request.args.get(k):
            try:
                q = q.filter(getattr(VisitRecap, k) == uuid.UUID(request.args[k]))
            except ValueError:
                raise bad_request(f"Invalid {k}")
            filtered = True
    if not filtered:
        q = q.filter(VisitRecap.created_by == g.user.id)
    return ok([svc.serialize(r) for r in q.order_by(VisitRecap.created_at.desc()).limit(50).all()])


@bp.get("/<uuid:rid>")
@protect("meetings.read")
def get_recap(rid):
    return ok(svc.serialize(_get(rid)))


@bp.post("")
@protect("meetings.create")
@limiter.limit("120 per hour")
def create_recap():
    """One recap per visit: posting again for the same meeting updates the existing one, so the link the family has keeps working."""
    d = parse(RecapIn)
    links = {k: getattr(d, k) for k in ("lead_id", "contact_id", "deal_id")}
    m = None
    if d.meeting_id:
        m = db.session.query(Meeting).filter(Meeting.id == d.meeting_id, Meeting.workspace_id == g.workspace.id, Meeting.deleted_at.is_(None)).one_or_none()
        if m is None:
            raise not_found("Site visit")
        links = {k: links[k] or getattr(m, k) for k in links}
    for k, model in (("lead_id", Lead), ("contact_id", Contact), ("deal_id", Deal)):
        ensure_ref(model, links[k], k)
    if not any(links.values()):
        raise ApiError(422, "validation_error", "Choose the buyer this recap is for", {"lead_id": "Required"})
    r = db.session.query(VisitRecap).filter(VisitRecap.workspace_id == g.workspace.id, VisitRecap.meeting_id == m.id, VisitRecap.revoked_at.is_(None)).first() if m else None
    status = 200
    if r is None:  # new: start from the flat(s) seen on this visit
        company_id = db.session.get(Contact, links["contact_id"]).company_id if links["contact_id"] else None
        r = VisitRecap(workspace_id=g.workspace.id, meeting_id=m.id if m else None, token=svc.new_token(), created_by=g.user.id, company_id=company_id,
                       unit_ids=svc.suggested_units(m) if m else [], photo_ids=[], **links)
        db.session.add(r)
        status = 201
    if d.unit_ids is not None:
        r.unit_ids = svc.check_units(d.unit_ids)
    if d.photo_ids is not None:
        r.photo_ids = svc.check_photos(d.photo_ids)
    r.project_id = (m.project_id if m else None) or (db.session.get(Unit, uuid.UUID(r.unit_ids[0])).project_id if r.unit_ids else None)
    db.session.flush()
    r.message = d.message if d.message is not None else (r.message or svc.default_message(r, g.user.name))
    db.session.commit()
    return (created if status == 201 else ok)(svc.serialize(r))


@bp.patch("/<uuid:rid>")
@protect("meetings.create")
def update_recap(rid):
    r = _get(rid)
    if r.revoked_at:
        raise conflict("This recap's link was switched off. Make a new recap instead.", "recap_revoked")
    d = parse(RecapPatch)
    if d.unit_ids is not None:
        r.unit_ids = svc.check_units(d.unit_ids)
    if d.photo_ids is not None:
        r.photo_ids = svc.check_photos(d.photo_ids)
    if d.message is not None:
        r.message = d.message
    db.session.commit()
    return ok(svc.serialize(r))


@bp.post("/<uuid:rid>/revoke")
@protect("meetings.create")
def revoke_recap(rid):
    r = _get(rid)
    if not r.revoked_at:
        r.revoked_at = utcnow()
        audit.record("visit_recap.revoked", entity_type="visit_recap", entity_id=r.id, summary="Switched off a visit recap link")
        db.session.commit()
    return ok(svc.serialize(r))


# ---- sending -----------------------------------------------------------------------------------------------------

def _whatsapp():
    if "whatsapp_integration" not in g.features:
        return None
    i = integrations.get(g.workspace.id, "whatsapp")
    return i if i and i.status in ("connected", "error") and i.credentials_enc else None


@bp.post("/<uuid:rid>/send")
@protect("meetings.create")
@limiter.limit("60 per hour")
def send_recap(rid):
    """Through the workspace's WhatsApp Business number when it can (so reps never need the buyer's number), else a
    wa.me link the rep opens on their phone. WhatsApp only allows free text within 24 hours of the buyer's last
    message; outside that it needs the approved recap template chosen in Integrations → WhatsApp."""
    r = _get(rid)
    if r.revoked_at:
        raise conflict("This recap's link was switched off. Make a new recap instead.", "recap_revoked")
    if not r.unit_ids and not r.photo_ids:
        raise ApiError(422, "validation_error", "Add the flats you showed, or a photo, before sending.", {"unit_ids": "Add a flat"})
    url = svc.public_url(r)
    body = (r.message or svc.default_message(r, g.user.name)).strip()
    text = f"{body}\n\n{url}"
    who = svc.buyer(r)
    i = _whatsapp()
    reason = None
    sent = None
    if who is None:
        reason = "This recap isn't linked to a lead or client, so pick the chat in WhatsApp."
    elif i is None:
        reason = "WhatsApp Business isn't connected, so the message opens in your WhatsApp."
    elif not wa.normalize_phone(who[1].phone):
        reason = f"{who[1].name} doesn't have a valid mobile number, so pick the chat in WhatsApp."
    else:
        etype, e = who
        phone = wa.normalize_phone(e.phone)
        template = (i.config or {}).get("recap_template")
        if wa.window_open(g.workspace.id, phone):
            sent = wa.send(i, etype, e, text=text)
        elif template:
            params = [e.first_name or "there", url][: int(template.get("body_params", 0))]
            sent = wa.send(i, etype, e, template={**template, "params": params})
        else:
            reason = (f"{e.name} hasn't messaged your WhatsApp Business number in the last 24 hours, so WhatsApp only allows an approved template. "
                      "Pick a visit recap template in Integrations → WhatsApp → Manage to send it from the CRM next time.")
    r.sent_at = utcnow()
    flats = len(r.unit_ids or [])
    title = f"Visit recap sent on WhatsApp ({flats} flat{'s' if flats != 1 else ''}, {len(r.photo_ids or [])} photo{'s' if len(r.photo_ids or []) != 1 else ''})"
    if sent is not None:
        r.sent_via = "whatsapp"
        activities.log_activity("visit_recap", title, body=url, data={"visit_recap_id": str(r.id), "whatsapp_message_id": str(sent.id)},
                                lead_id=r.lead_id, contact_id=r.contact_id, deal_id=r.deal_id, company_id=r.company_id, touch=False)
        audit.record("visit_recap.sent", entity_type="visit_recap", entity_id=r.id, summary=f"Sent a visit recap on WhatsApp to {who[1].name}")
        db.session.commit()
        return ok({"status": "sent", "url": url, "recap": svc.serialize(r)})
    # Fallback: open WhatsApp on the rep's phone. The number is only filled in for people allowed to see it.
    phone = wa.normalize_phone(who[1].phone) if who and privacy.can_view() else None
    r.sent_via = "whatsapp_link"
    activities.log_activity("visit_recap", title.replace("sent on", "shared through"), body=url, data={"visit_recap_id": str(r.id), "channel": "whatsapp_link"},
                            lead_id=r.lead_id, contact_id=r.contact_id, deal_id=r.deal_id, company_id=r.company_id)
    if who:
        mailbox.touch_contacted(SimpleNamespace(lead_id=r.lead_id, contact_id=r.contact_id), utcnow())
    audit.record("visit_recap.shared", entity_type="visit_recap", entity_id=r.id, summary="Shared a visit recap through a WhatsApp link")
    db.session.commit()
    return ok({"status": "link", "reason": reason, "url": url, "text": text, "recap": svc.serialize(r),
               "whatsapp_url": f"https://wa.me/{phone}?text={quote(text)}" if phone else f"https://wa.me/?text={quote(text)}"})


# ---- the public page ---------------------------------------------------------------------------------------------

def _public(token: str) -> VisitRecap:
    """Find the recap across workspaces by its token, then run the rest of the request inside that workspace."""
    if not token or len(token) < 20 or len(token) > 64:
        raise not_found("Recap")
    with bypass_scope():
        r = db.session.query(VisitRecap).filter(VisitRecap.token == token, VisitRecap.revoked_at.is_(None)).one_or_none()
        ws = db.session.get(Workspace, r.workspace_id) if r else None
        ws_id = ws.id if ws and not ws.deleted_at else None
    if r is None or ws_id is None:
        raise not_found("Recap")
    set_tenant(ws_id)
    g.workspace, g.user, g.permissions, g.features, g.member = db.session.get(Workspace, ws_id), None, set(), set(), None
    return db.session.get(VisitRecap, r.id)


@public_bp.get("/<token>")
@limiter.limit("120 per minute")
def public_recap(token):
    r = _public(token)
    data = svc.public_view(r)
    if request.args.get("meta") != "1":  # link previews (WhatsApp, the page's own metadata) don't count as opens
        svc.record_view(r)
        db.session.commit()
    return ok(data)


@public_bp.get("/<token>/files/<uuid:fid>")
@limiter.limit("300 per minute")
def public_file(token, fid):
    """A photo or brochure on the recap. Only files the recap shows can be fetched through its link."""
    r = _public(token)
    if fid not in svc.shared_file_ids(r):
        raise not_found("File")
    fa = db.session.query(FileAsset).filter(FileAsset.id == fid, FileAsset.deleted_at.is_(None)).one_or_none()
    if fa is None:
        raise not_found("File")
    st = storage.get_storage()
    if isinstance(st, storage.LocalStorage):
        path = st.open(fa.storage_key)
        if not path.exists():
            raise not_found("File")
        resp = send_file(path, mimetype=fa.mime_type, as_attachment=not fa.mime_type.startswith("image/") and fa.mime_type != "application/pdf", download_name=fa.filename)
        resp.headers["Content-Security-Policy"] = "sandbox"
        resp.headers["Cache-Control"] = "private, max-age=600"
        return resp
    return redirect(st.signed_url(fa.storage_key, fa.filename, expires=600))


class HoldIn(Schema):
    unit_id: uuid.UUID
    name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)


@public_bp.post("/<token>/hold")
@limiter.limit("10 per minute")
def public_hold(token):
    d = parse(HoldIn)
    r = _public(token)
    out = svc.request_hold(r, d.unit_id, d.name, d.note)
    db.session.commit()
    return ok(out)
