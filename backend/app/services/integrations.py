"""Integrations marketplace: catalog, connection state machine, and live clients.

States: not_connected -> connected -> (error | reconnect) -> connected.
`sandbox` mode is used when provider credentials aren't configured on the server so the product is fully explorable;
sandbox connections never call external APIs.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from email.message import EmailMessage
from typing import Any

import httpx
from flask import current_app

from app.core import crypto
from app.extensions import db
from app.models import Integration
from app.models.base import utcnow

log = logging.getLogger("app.integrations")

CATEGORIES = ["Communication", "Productivity", "Payments", "Marketing", "Analytics", "Developer tools"]

CATALOG: dict[str, dict] = {
    "gmail": {"name": "Gmail", "category": "Communication", "description": "Send and receive email from your Gmail account and auto-link it to contacts and deals.", "kind": "google", "scopes": ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]},
    "outlook": {"name": "Outlook", "category": "Communication", "description": "Connect Microsoft 365 / Outlook to send email and keep conversations in the CRM.", "kind": "microsoft", "scopes": ["Mail.Send", "Mail.Read", "offline_access"]},
    "slack": {"name": "Slack", "category": "Communication", "description": "Get deal and lead alerts in a Slack channel via an incoming webhook.", "kind": "webhook_url"},
    "microsoft_teams": {"name": "Microsoft Teams", "category": "Communication", "description": "Post CRM alerts to a Teams channel.", "kind": "sandbox"},
    "whatsapp": {"name": "WhatsApp Business", "category": "Communication", "description": "Message customers on WhatsApp from their CRM record.", "kind": "sandbox", "feature": "whatsapp_integration"},
    "zoom": {"name": "Zoom", "category": "Communication", "description": "Create Zoom links when you schedule meetings.", "kind": "sandbox"},
    "google_calendar": {"name": "Google Calendar", "category": "Productivity", "description": "Two-way sync of meetings and follow-ups with Google Calendar.", "kind": "google", "scopes": ["https://www.googleapis.com/auth/calendar.events"]},
    "google_contacts": {"name": "Google Contacts", "category": "Productivity", "description": "Import your Google Contacts into the CRM.", "kind": "google", "scopes": ["https://www.googleapis.com/auth/contacts.readonly"]},
    "google_sheets": {"name": "Google Sheets", "category": "Productivity", "description": "Export reports and pipeline snapshots to Google Sheets.", "kind": "google", "scopes": ["https://www.googleapis.com/auth/spreadsheets"]},
    "stripe": {"name": "Stripe", "category": "Payments", "description": "See customer payments and subscriptions on contact and company records.", "kind": "sandbox"},
    "razorpay": {"name": "Razorpay", "category": "Payments", "description": "Track Razorpay payments against deals and customers.", "kind": "sandbox"},
    "mailchimp": {"name": "Mailchimp", "category": "Marketing", "description": "Sync contacts to Mailchimp audiences.", "kind": "sandbox"},
    "meta_lead_ads": {"name": "Meta Lead Ads", "category": "Marketing", "description": "Capture Facebook & Instagram lead-ad submissions as leads.", "kind": "sandbox"},
    "google_analytics": {"name": "Google Analytics", "category": "Analytics", "description": "Attribute leads and revenue to marketing channels.", "kind": "sandbox"},
    "zapier": {"name": "Zapier", "category": "Developer tools", "description": "Connect 5,000+ apps using webhooks and your lead-capture form endpoint.", "kind": "webhooks"},
    "webhooks": {"name": "Webhooks", "category": "Developer tools", "description": "Send signed JSON events to your own endpoints when records change.", "kind": "webhooks"},
}
WEBHOOK_EVENTS = ["lead.created", "deal.created", "deal.stage_changed", "deal.won", "deal.lost", "task.completed", "contact.updated"]


def get(workspace_id, provider: str) -> Integration | None:
    return db.session.query(Integration).filter_by(workspace_id=workspace_id, provider=provider).one_or_none()


def upsert(workspace_id, provider: str, user_id=None) -> Integration:
    i = get(workspace_id, provider)
    if i is None:
        i = Integration(workspace_id=workspace_id, provider=provider, status="not_connected")
        db.session.add(i)
        db.session.flush()
    return i


def set_creds(i: Integration, creds: dict) -> None:
    i.credentials_enc = crypto.encrypt(json.dumps(creds))


def get_creds(i: Integration) -> dict:
    return json.loads(crypto.decrypt(i.credentials_enc)) if i.credentials_enc else {}


def public_view(provider: str, i: Integration | None) -> dict:
    meta = CATALOG[provider]
    cfg = dict(i.config or {}) if i else {}
    cfg.pop("signing_secret", None)
    return {"provider": provider, "name": meta["name"], "category": meta["category"], "description": meta["description"], "feature": meta.get("feature"),
            "status": i.status if i else "not_connected", "mode": i.mode if i else None, "account_label": i.account_label if i else None,
            "last_synced_at": i.last_synced_at.isoformat() if i and i.last_synced_at else None, "last_error": i.last_error if i else None, "config": cfg,
            "live_capable": meta["kind"] in ("webhook_url", "webhooks") or (meta["kind"] == "google" and bool(current_app.config["GOOGLE_CLIENT_ID"]))}


# ---- Google OAuth -------------------------------------------------------------------------

def google_auth_url(provider: str, state: str) -> str:
    from urllib.parse import urlencode

    cfg = current_app.config
    scopes = ["openid", "email"] + CATALOG[provider]["scopes"]
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": cfg["GOOGLE_CLIENT_ID"], "redirect_uri": f"{cfg['WEB_ORIGIN']}/api/v1/integrations/google/callback", "response_type": "code",
        "scope": " ".join(scopes), "access_type": "offline", "prompt": "consent", "state": state})


def google_exchange(code: str) -> dict:
    cfg = current_app.config
    r = httpx.post("https://oauth2.googleapis.com/token", data={"code": code, "client_id": cfg["GOOGLE_CLIENT_ID"], "client_secret": cfg["GOOGLE_CLIENT_SECRET"],
                                                                "redirect_uri": f"{cfg['WEB_ORIGIN']}/api/v1/integrations/google/callback", "grant_type": "authorization_code"}, timeout=15)
    r.raise_for_status()
    return r.json()


def _google_token(i: Integration) -> str:
    creds = get_creds(i)
    if creds.get("expires_at", 0) > time.time() + 60:
        return creds["access_token"]
    cfg = current_app.config
    r = httpx.post("https://oauth2.googleapis.com/token", data={"client_id": cfg["GOOGLE_CLIENT_ID"], "client_secret": cfg["GOOGLE_CLIENT_SECRET"],
                                                                "refresh_token": creds.get("refresh_token"), "grant_type": "refresh_token"}, timeout=15)
    if r.status_code >= 400:
        i.status, i.last_error = "reconnect", "Google access was revoked or expired. Reconnect to continue."
        raise RuntimeError(i.last_error)
    tok = r.json()
    creds.update(access_token=tok["access_token"], expires_at=time.time() + tok.get("expires_in", 3600))
    set_creds(i, creds)
    return creds["access_token"]


def _microsoft_token(i: Integration) -> str:
    creds = get_creds(i)
    if creds.get("expires_at", 0) > time.time() + 60:
        return creds["access_token"]
    cfg = current_app.config
    r = httpx.post("https://login.microsoftonline.com/common/oauth2/v2.0/token", data={"client_id": cfg.get("MICROSOFT_CLIENT_ID", ""), "client_secret": cfg.get("MICROSOFT_CLIENT_SECRET", ""),
                                                                                     "refresh_token": creds.get("refresh_token"), "grant_type": "refresh_token"}, timeout=15)
    if r.status_code >= 400:
        i.status, i.last_error = "reconnect", "Microsoft access expired. Reconnect to continue."
        raise RuntimeError(i.last_error)
    tok = r.json()
    creds.update(access_token=tok["access_token"], refresh_token=tok.get("refresh_token", creds.get("refresh_token")), expires_at=time.time() + tok.get("expires_in", 3600))
    set_creds(i, creds)
    return creds["access_token"]


def send_via_integration(i: Integration, to: str, cc: list[str], subject: str, html: str, from_addr: str | None) -> str | None:
    if i.provider == "gmail":
        msg = EmailMessage()
        msg["To"], msg["Subject"] = to, subject
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg.set_content("Please view this email in an HTML-capable client.")
        msg.add_alternative(html, subtype="html")
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        r = httpx.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", headers={"Authorization": f"Bearer {_google_token(i)}"}, json={"raw": raw}, timeout=20)
        if r.status_code in (401, 403):
            i.status, i.last_error = "reconnect", "Gmail rejected the request. Reconnect your account."
        r.raise_for_status()
        return r.json().get("id")
    if i.provider == "outlook":
        r = httpx.post("https://graph.microsoft.com/v1.0/me/sendMail", headers={"Authorization": f"Bearer {_microsoft_token(i)}"}, timeout=20, json={
            "message": {"subject": subject, "body": {"contentType": "HTML", "content": html}, "toRecipients": [{"emailAddress": {"address": to}}],
                        "ccRecipients": [{"emailAddress": {"address": c}} for c in cc]}})
        r.raise_for_status()
        return None
    raise RuntimeError("Unsupported mailbox provider")


def push_meeting(workspace_id, meeting) -> None:
    """Create a Google Calendar event for a CRM meeting when Google Calendar is connected live."""
    i = get(workspace_id, "google_calendar")
    if i is None or i.status != "connected" or i.mode != "live" or meeting.external_event_id:
        return
    try:
        r = httpx.post("https://www.googleapis.com/calendar/v3/calendars/primary/events", headers={"Authorization": f"Bearer {_google_token(i)}"}, timeout=15, json={
            "summary": meeting.title, "description": meeting.description or "", "location": meeting.location or meeting.meeting_url or "",
            "start": {"dateTime": meeting.starts_at.isoformat()}, "end": {"dateTime": meeting.ends_at.isoformat()},
            "attendees": [{"email": a["email"]} for a in meeting.attendees if a.get("email")]})
        r.raise_for_status()
        meeting.external_event_id = r.json().get("id")
    except Exception as e:
        i.status, i.last_error = "error", f"Calendar sync failed: {str(e)[:200]}"
        log.warning("calendar push failed: %s", e)


# ---- Outbound events (webhooks + Slack) -------------------------------------------------

def publish(workspace_id, event: str, payload: dict) -> None:
    from app.services.automation import safe_url

    rows = db.session.query(Integration).filter(Integration.workspace_id == workspace_id, Integration.status == "connected", Integration.provider.in_(("webhooks", "slack", "zapier"))).all()
    for i in rows:
        try:
            if i.provider == "slack":
                if event not in ("deal.won", "deal.lost", "lead.created") and not (event == "deal.stage_changed"):
                    continue
                url = get_creds(i).get("webhook_url")
                if url and safe_url(url):
                    text = {"lead.created": f":sparkles: New lead: *{payload.get('name', '')}*", "deal.stage_changed": f":arrow_right: *{payload.get('name', 'Deal')}* moved to {payload.get('stage', '')}",
                            "deal.won": f":tada: Deal won: *{payload.get('name', '')}*", "deal.lost": f"Deal lost: *{payload.get('name', '')}*"}.get(event, event)
                    httpx.post(url, json={"text": text}, timeout=5, follow_redirects=False)
            else:
                secret = (i.config or {}).get("signing_secret", "")
                body = json.dumps({"event": event, "data": payload, "workspace_id": str(workspace_id), "sent_at": utcnow().isoformat()}, separators=(",", ":"))
                sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
                for ep in (i.config or {}).get("endpoints", []):
                    if event in ep.get("events", []) and safe_url(ep["url"]):
                        httpx.post(ep["url"], content=body, headers={"Content-Type": "application/json", "X-CRM-Signature": f"sha256={sig}", "X-CRM-Event": event}, timeout=5, follow_redirects=False)
            i.last_synced_at = utcnow()
        except Exception as e:  # never let a customer endpoint break CRM actions; surface as an Error state
            i.status, i.last_error = "error", f"Delivery failed: {str(e)[:200]}"
            log.warning("outbound publish failed (%s): %s", i.provider, e)


def new_signing_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(24)
