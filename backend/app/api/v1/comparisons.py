"""Flat and society comparisons: side-by-side preview, PDF download, and sharing the PDF with a client by email or WhatsApp."""
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
from app.services import activities, audit, mailbox, storage
from app.services import comparison as cmp
from app.services import society_comparison as soc
from app.services.usage import check_limit

bp = Blueprint("comparisons", __name__, url_prefix="/api/v1/comparisons")
public_bp = Blueprint("public_comparisons", __name__, url_prefix="/api/v1/public/comparisons")


class PdfIn(Schema):
    unit_ids: list[uuid.UUID] = Field(min_length=1, max_length=cmp.MAX_FLATS)
    title: str | None = Field(default=None, max_length=120)
    client_name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class SendIn(Schema):
    channel: Literal["email", "whatsapp"]
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    to: list[Email] = Field(default_factory=list, max_length=10)
    phone: str | None = Field(default=None, max_length=40)
    subject: str | None = Field(default=None, max_length=300)
    message: str | None = Field(default=None, max_length=5000)


class ShareIn(PdfIn, SendIn):
    pass


class SocietyPick(Schema):
    project_id: uuid.UUID
    sizes: list[str] | None = Field(default=None, max_length=20)  # layouts to show and attach; None means all
    photo_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)


class SocietyPreviewIn(Schema):
    societies: list[SocietyPick] = Field(min_length=1, max_length=soc.MAX_SOCIETIES)


class SocietyPdfIn(SocietyPreviewIn):
    title: str | None = Field(default=None, max_length=120)
    client_name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


class SocietyShareIn(SocietyPdfIn, SendIn):
    pass


def _ids_arg() -> list[uuid.UUID]:
    out = []
    for raw in request.args.get("ids", "").split(","):
        if raw.strip():
            try:
                out.append(uuid.UUID(raw.strip()))
            except ValueError:
                raise ApiError(422, "validation_error", "Invalid flat id", {"ids": raw})
    return out


def _pdf(d: PdfIn) -> tuple[dict, bytes]:
    data = cmp.build(cmp.load_units(d.unit_ids))
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
    data, pdf = _pdf(d)
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
    rel = _check_send(d)
    data, pdf = _pdf(d)
    flats = ", ".join(f["title"] for f in data["flats"])
    return _send(d, rel, pdf, cmp.filename(data), what="Flat comparison", things=flats)


def _check_send(d: SendIn) -> dict:
    """Checks the recipient before the PDF is made; returns the lead / contact / company the share is filed under."""
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
    return rel


def _send(d: SendIn, rel: dict, pdf: bytes, name: str, *, what: str, things: str):
    """Stores the PDF as a file on the lead / client, then emails it or hands back a WhatsApp link to it."""
    if d.channel == "email" and len(pdf) > soc.EMAIL_LIMIT_MB * 1024 * 1024:
        raise ApiError(422, "too_big_for_email", f"The PDF is {len(pdf) / 1048576:.0f} MB, too big to email (the limit is {soc.EMAIL_LIMIT_MB} MB). "
                       "Leave out some photos or layouts, or send it on WhatsApp.")
    key = storage.new_key(g.workspace.id, name)
    storage.get_storage().put(key, io.BytesIO(pdf), "application/pdf")
    fa = FileAsset(workspace_id=g.workspace.id, filename=name, storage_key=key, mime_type="application/pdf", size_bytes=len(pdf), uploaded_by=g.user.id,
                   **{k: v for k, v in rel.items() if k in ("lead_id", "contact_id", "company_id")})
    db.session.add(fa)
    db.session.flush()

    if d.channel == "email":
        subject = d.subject or f"{what}: {{{{first_name}}}}"
        body = d.message or f"Hi {{{{first_name}}}},\n\nAs discussed, here is a side-by-side comparison of {things}. The PDF is attached.\n\nHappy to arrange site visits for any of these.\n\n{{{{sender_name}}}}"
        ctx = {"sender_name": g.user.name, "first_name": (d.client_name or "").split(" ")[0] or "there"}
        if rel.get("contact_id"):
            c = db.session.get(Contact, rel["contact_id"])
            ctx.update(first_name=c.first_name, last_name=c.last_name or "", company=c.company.name if c.company else "")
        elif rel.get("lead_id"):
            l = db.session.get(Lead, rel["lead_id"])
            ctx.update(first_name=l.first_name, last_name=l.last_name or "", company=l.company_name or "")
        email = mailbox.send_crm_email(g.user, to=d.to, cc=[], subject=mailbox.merge_fields(subject, ctx), body=mailbox.merge_fields(body, ctx),
                                       track=True, related=rel, attachment_file_ids=[str(fa.id)])
        audit.record("comparison.shared", entity_type="file", entity_id=fa.id, summary=f"Emailed a comparison of {things} to {', '.join(d.to)}")
        db.session.commit()
        if email.status == "failed":
            raise ApiError(502, "delivery_failed", f"The email couldn't be delivered: {email.error or 'unknown error'}")
        return ok({"channel": "email", "status": email.status, "file_id": str(fa.id), "email_id": str(email.id)})

    link = cmp.public_url(fa.id)
    text = (d.message or f"Hi {(d.client_name or '').split(' ')[0] or 'there'}, here is the comparison of {things} we discussed.").strip() + f"\n\n{link}"
    phone = _phone_digits(d.phone)
    activities.log_activity("file", f"{what} sent on WhatsApp", body=f"{things}\n{link}", data={"file_id": str(fa.id), "channel": "whatsapp"},
                            lead_id=rel.get("lead_id"), contact_id=rel.get("contact_id"), company_id=rel.get("company_id"))
    if rel.get("lead_id") or rel.get("contact_id"):
        mailbox.touch_contacted(SimpleNamespace(lead_id=rel.get("lead_id"), contact_id=rel.get("contact_id")), utcnow())
    audit.record("comparison.shared", entity_type="file", entity_id=fa.id, summary=f"Shared a comparison of {things} on WhatsApp")
    db.session.commit()
    return ok({"channel": "whatsapp", "file_id": str(fa.id), "pdf_url": link, "text": text,
               "whatsapp_url": f"https://wa.me/{phone}?text={quote(text)}" if phone else f"https://wa.me/?text={quote(text)}"})


# ---- societies -------------------------------------------------------------------------------------------------------

def _society_data(d: SocietyPreviewIn):
    projects = soc.load_projects([x.project_id for x in d.societies])
    picks = {x.project_id: x.model_dump() for x in d.societies}
    return projects, picks, soc.build(projects, picks)


def _society_pdf(d: SocietyPdfIn) -> tuple[dict, bytes]:
    projects, picks, data = _society_data(d)
    pdf = soc.render_pdf(data, soc.attachments(projects, picks), projects, title=d.title or "Society comparison", client_name=d.client_name, note=d.note,
                         prepared_by=g.user.name, workspace_name=g.workspace.name)
    return data, pdf


@bp.post("/societies/preview")
@protect("projects.read")
def society_preview():
    return ok(_society_data(parse(SocietyPreviewIn))[2])


@bp.post("/societies/pdf")
@protect("projects.read")
def society_pdf():
    data, pdf = _society_pdf(parse(SocietyPdfIn))
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": _disposition(soc.filename(data))})


def _disposition(name: str) -> str:
    """Society names can be in any script; headers must be ASCII, so send a plain fallback plus the real name."""
    plain = name.encode("ascii", "ignore").decode().replace('"', "") or "Society comparison.pdf"
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name)}"


@bp.post("/societies/share")
@protect("projects.read")
@limiter.limit("60 per hour")
def society_share():
    d = parse(SocietyShareIn)
    rel = _check_send(d)
    data, pdf = _society_pdf(d)
    names = ", ".join(s["name"] for s in data["societies"])
    return _send(d, rel, pdf, soc.filename(data), what="Society comparison", things=names)


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
