"""Flat comparison: side-by-side preview, PDF download, and sharing the PDF with a client by email or WhatsApp."""
from __future__ import annotations

import hmac
import io
import re
import uuid
from types import SimpleNamespace
from typing import Literal
from urllib.parse import quote

from flask import Blueprint, Response, g, redirect, request, send_file
from pydantic import Field

from app.core.auth import protect, require
from app.core.crud import ensure_ref
from app.core.errors import ApiError, not_found
from app.core.responses import ok
from app.core.tenant import bypass_scope
from app.extensions import db, limiter
from app.models import Contact, FileAsset, Lead
from app.models.base import utcnow
from app.schemas.common import Email, Schema, parse
from app.services import activities, audit, inventory, mailbox, storage
from app.services import comparison as cmp
from app.services.usage import check_limit

bp = Blueprint("comparisons", __name__, url_prefix="/api/v1/comparisons")
public_bp = Blueprint("public_comparisons", __name__, url_prefix="/api/v1/public/comparisons")


class PdfIn(Schema):
    unit_ids: list[uuid.UUID] = Field(min_length=1, max_length=cmp.MAX_FLATS)
    title: str | None = Field(default=None, max_length=120)
    client_name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class ShareIn(PdfIn):
    channel: Literal["email", "whatsapp"]
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    to: list[Email] = Field(default_factory=list, max_length=10)
    phone: str | None = Field(default=None, max_length=40)
    subject: str | None = Field(default=None, max_length=300)
    message: str | None = Field(default=None, max_length=5000)


def _ids_arg() -> list[uuid.UUID]:
    out = []
    for raw in request.args.get("ids", "").split(","):
        if raw.strip():
            try:
                out.append(uuid.UUID(raw.strip()))
            except ValueError:
                raise ApiError(422, "validation_error", "Invalid flat id", {"ids": raw})
    return out


def _pdf(d: PdfIn, note: str) -> tuple[dict, bytes]:
    units = cmp.load_units(d.unit_ids)
    for u in units:  # a flat that keeps getting compared is in demand (read by airline-style pricing)
        inventory.log_event(u, "compared", note=note)
    data = cmp.build(units)
    pdf = cmp.render_pdf(data, title=d.title or "Flat comparison", client_name=d.client_name, note=d.note,
                         prepared_by=g.user.name, workspace_name=g.workspace.name)
    return data, pdf


@bp.get("/preview")
@protect("units.read")
def preview():
    return ok(cmp.build(cmp.load_units(_ids_arg())))


@bp.post("/pdf")
@protect("units.read")
def download_pdf():
    d = parse(PdfIn)
    data, pdf = _pdf(d, "Comparison PDF downloaded" + (f" for {d.client_name}" if d.client_name else ""))
    db.session.commit()
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="{cmp.filename(data)}"'})


def _phone_digits(raw: str | None) -> str:
    """wa.me wants the full number with country code and no symbols. Indian 10-digit mobiles get +91."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return "91" + digits if len(digits) == 10 else digits


@bp.post("/share")
@protect("units.read")
@limiter.limit("60 per hour")
def share():
    d = parse(ShareIn)
    require("files.create")
    rel: dict = {}
    if d.lead_id:
        ensure_ref(Lead, d.lead_id, "lead_id")
        rel["lead_id"] = d.lead_id
    if d.contact_id:
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

    data, pdf = _pdf(d, f"Comparison sent by {'email' if d.channel == 'email' else 'WhatsApp'}" + (f" to {d.client_name}" if d.client_name else ""))
    name = cmp.filename(data)
    key = storage.new_key(g.workspace.id, name)
    storage.get_storage().put(key, io.BytesIO(pdf), "application/pdf")
    fa = FileAsset(workspace_id=g.workspace.id, filename=name, storage_key=key, mime_type="application/pdf", size_bytes=len(pdf), uploaded_by=g.user.id,
                   **{k: v for k, v in rel.items() if k in ("lead_id", "contact_id", "company_id")})
    db.session.add(fa)
    db.session.flush()
    flats = ", ".join(f["title"] for f in data["flats"])

    if d.channel == "email":
        subject = d.subject or "Flat comparison: {{first_name}}"
        body = d.message or f"Hi {{{{first_name}}}},\n\nAs discussed, here is a side-by-side comparison of {flats}. The PDF is attached.\n\nHappy to arrange site visits for any of these.\n\n{{{{sender_name}}}}"
        ctx = {"sender_name": g.user.name, "first_name": (d.client_name or "").split(" ")[0] or "there"}
        if rel.get("contact_id"):
            c = db.session.get(Contact, rel["contact_id"])
            ctx.update(first_name=c.first_name, last_name=c.last_name or "", company=c.company.name if c.company else "")
        elif rel.get("lead_id"):
            l = db.session.get(Lead, rel["lead_id"])
            ctx.update(first_name=l.first_name, last_name=l.last_name or "", company=l.company_name or "")
        email = mailbox.send_crm_email(g.user, to=d.to, cc=[], subject=mailbox.merge_fields(subject, ctx), body=mailbox.merge_fields(body, ctx),
                                       track=True, related=rel, attachment_file_ids=[str(fa.id)])
        audit.record("comparison.shared", entity_type="file", entity_id=fa.id, summary=f"Emailed a comparison of {flats} to {', '.join(d.to)}")
        db.session.commit()
        if email.status == "failed":
            raise ApiError(502, "delivery_failed", f"The email couldn't be delivered: {email.error or 'unknown error'}")
        return ok({"channel": "email", "status": email.status, "file_id": str(fa.id), "email_id": str(email.id)})

    link = cmp.public_url(fa.id)
    text = (d.message or f"Hi {(d.client_name or '').split(' ')[0] or 'there'}, here is the comparison of {flats} we discussed.").strip() + f"\n\n{link}"
    phone = _phone_digits(d.phone)
    activities.log_activity("file", "Flat comparison sent on WhatsApp", body=f"{flats}\n{link}", data={"file_id": str(fa.id), "channel": "whatsapp"},
                            lead_id=rel.get("lead_id"), contact_id=rel.get("contact_id"), company_id=rel.get("company_id"))
    if rel.get("lead_id") or rel.get("contact_id"):
        mailbox.touch_contacted(SimpleNamespace(lead_id=rel.get("lead_id"), contact_id=rel.get("contact_id")), utcnow())
    audit.record("comparison.shared", entity_type="file", entity_id=fa.id, summary=f"Shared a comparison of {flats} on WhatsApp")
    db.session.commit()
    return ok({"channel": "whatsapp", "file_id": str(fa.id), "pdf_url": link, "text": text,
               "whatsapp_url": f"https://wa.me/{phone}?text={quote(text)}" if phone else f"https://wa.me/?text={quote(text)}"})


@public_bp.get("/<uuid:fid>/<sig>.pdf")
@limiter.limit("60 per minute")
def public_pdf(fid, sig):
    """The link inside the WhatsApp message. Signed per file, so it can't be guessed; works without logging in."""
    if not hmac.compare_digest(cmp.public_sig(fid), sig):
        raise not_found("File")
    with bypass_scope():
        fa = db.session.query(FileAsset).filter(FileAsset.id == fid, FileAsset.deleted_at.is_(None)).one_or_none()
        key, name = (fa.storage_key, fa.filename) if fa else (None, None)
    if not key:
        raise not_found("File")
    st = storage.get_storage()
    if isinstance(st, storage.LocalStorage):
        path = st.open(key)
        if not path.exists():
            raise not_found("File")
        resp = send_file(path, mimetype="application/pdf", as_attachment=False, download_name=name)
        resp.headers["Content-Security-Policy"] = "sandbox"
        return resp
    return redirect(st.signed_url(key, name, expires=600))
