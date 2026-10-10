"""CRM email sending: associates mail with records, applies tracking, picks the connected mailbox or platform fallback."""
from __future__ import annotations

import html
import logging
import re
import uuid

from flask import current_app, g

from app.core import crypto
from app.extensions import db
from app.models import Contact, Email, Integration, Lead, User
from app.models.base import utcnow
from app.services import activities
from app.services import email as email_service

log = logging.getLogger("app.mailbox")


def text_to_html(body: str) -> str:
    esc = html.escape(body)
    esc = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', esc)
    return "<div style='font-family:Arial,sans-serif;font-size:14px;line-height:1.6'>" + esc.replace("\n", "<br>") + "</div>"


def merge_fields(text: str, ctx: dict[str, str]) -> str:
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: ctx.get(m.group(1), m.group(0)), text)


def match_records(addresses: list[str]) -> dict:
    """Find the contact/lead (and its company) for the first recognised address."""
    out: dict = {}
    for a in addresses:
        a = a.lower()
        c = db.session.query(Contact).filter(Contact.workspace_id == g.workspace.id, Contact.deleted_at.is_(None), Contact.email.ilike(a)).first()
        if c:
            out.update(contact_id=c.id, company_id=c.company_id)
            break
        l = db.session.query(Lead).filter(Lead.workspace_id == g.workspace.id, Lead.deleted_at.is_(None), Lead.email.ilike(a)).first()
        if l:
            out.update(lead_id=l.id)
            break
    return out


def _mailbox_integration(workspace_id, user_id) -> Integration | None:
    """The sender's OWN connected mailbox. Never another teammate's: mail must only leave through the account of the person sending it."""
    return db.session.query(Integration).filter(
        Integration.workspace_id == workspace_id, Integration.connected_by == user_id,
        Integration.provider.in_(("gmail", "outlook")), Integration.status == "connected",
    ).order_by(Integration.updated_at.desc()).first()


def sender_info(user: User) -> dict:
    """How this user's emails will go out - shown in the compose dialog."""
    integ = _mailbox_integration(g.workspace.id, user.id)
    verified = bool(user.email_verified_at)
    if integ is not None and integ.mode == "live":
        return {"mode": integ.provider, "address": integ.account_label or user.email, "verified": verified}
    return {"mode": "platform", "address": user.email, "verified": verified,
            "platform_from": current_app.config["EMAIL_FROM"]}


def deliver(email: Email, sender: User) -> None:
    """Actually send an Email row. Marks it sent/failed; never raises."""
    integ = _mailbox_integration(email.workspace_id, sender.id)
    body_html = text_to_html(email.body)
    if email.tracking_id:
        body_html += f"<img src='{current_app.config['WEB_ORIGIN']}/api/v1/public/t/{email.tracking_id}.gif' width='1' height='1' alt='' style='display:none'>"
    try:
        for to in email.to_addresses:
            if integ is not None and integ.mode == "live":
                from app.services.integrations import send_via_integration

                email.provider_message_id = send_via_integration(integ, to, email.cc_addresses, email.subject, body_html, email.from_address)
                email.provider = integ.provider
            else:
                # Sandbox/platform path: send as platform address with the rep as Reply-To.
                email.provider = f"{integ.provider}:sandbox" if integ else "platform"
                email_service.send_raw(to, email.subject, body_html, workspace_id=email.workspace_id, reply_to=sender.email, template_key="crm_email", from_name=sender.name)
        email.status, email.sent_at, email.error = "sent", utcnow(), None
    except Exception as e:
        log.exception("crm email failed")
        email.status, email.error = "failed", str(e)[:300]


def send_crm_email(sender: User, *, to: list[str], cc: list[str], subject: str, body: str, track: bool, scheduled_at=None,
                   related: dict, attachment_file_ids: list[str]) -> Email:
    rel = {k: v for k, v in related.items() if v}
    if not rel:
        rel = match_records(to)
    email = Email(
        workspace_id=g.workspace.id, direction="outbound", status="scheduled" if scheduled_at else "sent", subject=subject, body=body,
        from_address=sender.email, to_addresses=to, cc_addresses=cc, user_id=sender.id, scheduled_at=scheduled_at,
        tracking_id=uuid.uuid4().hex[:24] if track and "email_tracking" in g.features else None,
        thread_id=uuid.uuid4().hex[:20], attachment_file_ids=attachment_file_ids, **rel,
    )
    db.session.add(email)
    db.session.flush()
    if not scheduled_at:
        deliver(email, sender)
        now = utcnow()
        activities.log_activity("email", f"Email sent: {subject}", body=body[:500], lead_id=email.lead_id, contact_id=email.contact_id,
                                company_id=email.company_id, deal_id=email.deal_id, data={"email_id": str(email.id), "to": to})
        touch_contacted(email, now)
    return email


def touch_contacted(rec, when) -> None:
    if getattr(rec, "lead_id", None):
        lead = db.session.get(Lead, rec.lead_id)
        if lead:
            lead.last_contacted_at = when
            if lead.status == "new":
                lead.status = "contacted"
    if getattr(rec, "contact_id", None):
        c = db.session.get(Contact, rec.contact_id)
        if c:
            c.last_contacted_at = when


def decrypt_creds(integ: Integration) -> dict:
    import json

    return json.loads(crypto.decrypt(integ.credentials_enc)) if integ.credentials_enc else {}
