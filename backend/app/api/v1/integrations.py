from __future__ import annotations

import uuid

from flask import Blueprint, current_app, g, redirect, request
from pydantic import Field

from app.core.auth import protect
from app.core.errors import ApiError, bad_request, not_found
from app.core.responses import ok
from app.extensions import db
from app.models import Contact, Integration
from app.models.base import utcnow
from app.schemas.common import Schema, parse
from app.services import accounts, activities, audit, integrations as svc
from app.services.automation import safe_url
from app.services.usage import check_limit

bp = Blueprint("integrations", __name__, url_prefix="/api/v1/integrations")


def _meta(provider: str) -> dict:
    if provider not in svc.CATALOG:
        raise not_found("Integration")
    m = svc.CATALOG[provider]
    if m.get("feature") and m["feature"] not in g.features:
        raise ApiError(402, "feature_unavailable", f"{m['name']} isn't included in your current plan.", {"feature": m["feature"]})
    return m


@bp.get("")
@protect()
def list_():
    rows = {i.provider: i for i in db.session.query(Integration).filter_by(workspace_id=g.workspace.id)}
    return ok({"categories": svc.CATEGORIES, "integrations": [svc.public_view(p, rows.get(p)) for p in svc.CATALOG], "webhook_events": svc.WEBHOOK_EVENTS,
               "lead_form": {"token": (g.workspace.settings or {}).get("public_form_token"), "endpoint": f"{current_app.config['WEB_ORIGIN']}/api/v1/public/forms/{(g.workspace.settings or {}).get('public_form_token')}"}})


class ConnectIn(Schema):
    webhook_url: str | None = Field(default=None, max_length=500)
    endpoints: list[dict] | None = None


@bp.post("/<provider>/connect")
@protect("integrations.manage")
def connect(provider):
    meta = _meta(provider)
    body = parse(ConnectIn, request.get_json(silent=True) or {})
    i = svc.upsert(g.workspace.id, provider)
    kind = meta["kind"]
    if kind == "google" and current_app.config["GOOGLE_CLIENT_ID"]:
        state = accounts.signed_token("integ_oauth", f"{g.workspace.id}:{provider}:{g.user.id}", 15)
        return ok({"auth_url": svc.google_auth_url(provider, state)})
    if kind == "webhook_url":
        if not body.webhook_url or not body.webhook_url.startswith("https://hooks.slack.com/"):
            raise ApiError(422, "validation_error", "Paste a Slack incoming webhook URL (https://hooks.slack.com/…)", {"webhook_url": "Invalid Slack webhook URL"})
        svc.set_creds(i, {"webhook_url": body.webhook_url})
        i.mode, i.account_label = "live", "Slack webhook"
    elif kind == "webhooks":
        eps = []
        for ep in (body.endpoints or []):
            url = str(ep.get("url", ""))
            if not url.startswith("https://") or not safe_url(url):
                raise ApiError(422, "validation_error", f"“{url}” isn't a valid public https endpoint", {"endpoints": "Invalid URL"})
            eps.append({"url": url, "events": [e for e in ep.get("events", []) if e in svc.WEBHOOK_EVENTS] or svc.WEBHOOK_EVENTS})
        if provider == "webhooks" and not eps:
            raise ApiError(422, "validation_error", "Add at least one https endpoint", {"endpoints": "Required"})
        secret = (i.config or {}).get("signing_secret") or svc.new_signing_secret()
        i.config = {"endpoints": eps, "signing_secret": secret}
        i.mode, i.account_label = "live", f"{len(eps)} endpoint(s)"
        i.status, i.last_error, i.connected_by = "connected", None, g.user.id
        audit.record("integration.connected", entity_type="integration", entity_id=i.id, summary=f"Connected {meta['name']}")
        db.session.commit()
        return ok({**svc.public_view(provider, i), "signing_secret": secret})
    else:
        i.mode, i.account_label = "sandbox", f"{g.user.email} (sandbox)"
    i.status, i.last_error, i.connected_by = "connected", None, g.user.id
    audit.record("integration.connected", entity_type="integration", entity_id=i.id, summary=f"Connected {meta['name']} ({i.mode})")
    db.session.commit()
    return ok(svc.public_view(provider, i))


@bp.get("/google/callback")
@protect("integrations.manage", workspace=False, allow_restricted=True)
def google_callback():
    web = current_app.config["WEB_ORIGIN"]
    try:
        claims = accounts.read_token(request.args.get("state", ""), "integ_oauth")
        wid, provider, uid = claims["sub"].split(":")
        if uid != str(g.user.id) or provider not in svc.CATALOG:
            raise ValueError("state mismatch")
        tok = svc.google_exchange(request.args["code"])
    except Exception:
        return redirect(f"{web}/app/integrations?error=oauth_failed")
    from app.core.tenant import set_tenant

    set_tenant(uuid.UUID(wid))
    i = svc.upsert(uuid.UUID(wid), provider)
    import time

    svc.set_creds(i, {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"), "expires_at": time.time() + tok.get("expires_in", 3600)})
    i.status, i.mode, i.last_error, i.account_label, i.connected_by = "connected", "live", None, g.user.email, g.user.id
    audit.record("integration.connected", entity_type="integration", entity_id=i.id, workspace_id=uuid.UUID(wid), summary=f"Connected {svc.CATALOG[provider]['name']} (live)")
    db.session.commit()
    return redirect(f"{web}/app/integrations?connected={provider}")


@bp.post("/<provider>/disconnect")
@protect("integrations.manage")
def disconnect(provider):
    _meta(provider)
    i = svc.get(g.workspace.id, provider)
    if i is None:
        return ok(svc.public_view(provider, None))
    i.status, i.credentials_enc, i.last_error, i.account_label, i.config = "not_connected", None, None, None, {}
    audit.record("integration.disconnected", entity_type="integration", entity_id=i.id, summary=f"Disconnected {svc.CATALOG[provider]['name']}")
    db.session.commit()
    return ok(svc.public_view(provider, i))


@bp.post("/<provider>/sync")
@protect("integrations.manage")
def sync(provider):
    _meta(provider)
    i = svc.get(g.workspace.id, provider)
    if i is None or i.status != "connected":
        raise ApiError(409, "not_connected", "Connect this integration first.")
    imported = 0
    if provider == "google_contacts" and i.mode == "sandbox":
        check_limit(g.workspace, "contacts", 5)
        samples = [("Priya", "Nair", "priya.nair@example.org", "Product Manager"), ("Arjun", "Mehta", "arjun.mehta@example.org", "Founder"), ("Sana", "Khan", "sana.khan@example.org", "Marketing Lead"),
                   ("Rohan", "Das", "rohan.das@example.org", "Operations"), ("Meera", "Iyer", "meera.iyer@example.org", "Director")]
        for f, l, e, t in samples:
            if not db.session.query(Contact.id).filter(Contact.workspace_id == g.workspace.id, Contact.email == e, Contact.deleted_at.is_(None)).first():
                c = Contact(workspace_id=g.workspace.id, first_name=f, last_name=l, email=e, job_title=t, owner_id=g.user.id, tags=["google-sandbox"])
                db.session.add(c)
                db.session.flush()
                activities.log_activity("created", "Contact imported from Google Contacts (sandbox)", contact_id=c.id)
                imported += 1
    i.last_synced_at = utcnow()
    db.session.commit()
    return ok({"imported": imported, "integration": svc.public_view(provider, i)})


@bp.post("/<provider>/simulate-error")
@protect("integrations.manage")
def simulate_error(provider):
    """Dev/demo helper to exercise Error + Reconnect states."""
    if current_app.config["ENV"] == "production":
        raise not_found("Endpoint")
    _meta(provider)
    i = svc.get(g.workspace.id, provider)
    if i is None or i.status == "not_connected":
        raise ApiError(409, "not_connected", "Connect this integration first.")
    state = request.get_json(silent=True, force=True) or {}
    i.status = "reconnect" if state.get("state") == "reconnect" else "error"
    i.last_error = "Authorization expired. Reconnect to continue syncing." if i.status == "reconnect" else "Last sync failed: upstream returned 503."
    db.session.commit()
    return ok(svc.public_view(provider, i))


@bp.post("/webhooks/test")
@protect("integrations.manage")
def test_webhooks():
    i = svc.get(g.workspace.id, "webhooks")
    if i is None or i.status != "connected":
        raise ApiError(409, "not_connected", "Connect Webhooks first.")
    svc.publish(g.workspace.id, "lead.created", {"name": "Test Lead", "test": True})
    db.session.commit()
    return ok(svc.public_view("webhooks", i))
