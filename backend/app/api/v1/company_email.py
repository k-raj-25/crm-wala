"""Company email: the owner connects the firm's own email account once (Settings → Email), and everyone's CRM email goes out through it."""
from __future__ import annotations

from flask import Blueprint, g
from pydantic import Field

from app.core.auth import protect
from app.core.errors import ApiError
from app.core.responses import ok
from app.extensions import db
from app.schemas.common import Schema, parse
from app.services import audit, company_email as svc, integrations

bp = Blueprint("company_email", __name__, url_prefix="/api/v1/emails/company")


def _owner_only() -> None:
    if g.member.role.key != "owner":
        raise ApiError(403, "owner_only", "Only the workspace owner can change the company email.")


@bp.get("")
@protect("emails.read")
def get():
    v = svc.view(svc.get(g.workspace.id))
    if g.member.role.key != "owner":  # others only need to know whether it's set up and which address mail comes from
        v = {k: v[k] for k in ("status", "from_address", "own_address")}
    return ok(v)


class CompanyEmailIn(Schema):
    preset: str | None = Field(default="other", max_length=20)
    host: str | None = Field(default=None, max_length=200)
    port: int = Field(default=587, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=500)  # blank keeps the saved one
    from_address: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    from_name: str | None = Field(default=None, max_length=80)
    own_address: bool = False


@bp.put("")
@protect("emails.read")
def save():
    _owner_only()
    d = parse(CompanyEmailIn)
    i = integrations.upsert(g.workspace.id, svc.PROVIDER)
    old = integrations.get_creds(i) if i.credentials_enc else {}
    preset = svc.PRESETS.get(d.preset or "other", svc.PRESETS["other"])
    creds = {"host": (d.host or "").strip() or preset["host"], "port": d.port, "username": (d.username or "").strip() or d.from_address.strip(),
             "password": d.password or old.get("password", "")}
    missing = {k: "Required" for k in ("host", "password") if not creds[k]}
    if missing:
        raise ApiError(422, "validation_error", "Fill in the server and password.", missing)
    try:
        svc.verify(creds)
    except ValueError as e:
        raise ApiError(422, "email_login_failed", str(e), {"password": str(e)}) from e
    integrations.set_creds(i, creds)
    i.config = {"preset": d.preset if d.preset in svc.PRESETS else "other", "from_address": d.from_address.strip(),
                "from_name": (d.from_name or "").strip(), "own_address": d.own_address}
    i.status, i.mode, i.last_error, i.account_label, i.connected_by = "connected", "live", None, d.from_address.strip(), g.user.id
    audit.record("integration.connected", entity_type="integration", entity_id=i.id, summary=f"Connected company email ({i.account_label})")
    db.session.commit()
    return ok(svc.view(i))


@bp.post("/test")
@protect("emails.read")
def test():
    _owner_only()
    i = svc.active(g.workspace.id)
    if i is None:
        raise ApiError(409, "not_connected", "Connect the company email first.")
    try:
        svc.send(i, g.user, g.user.email, [], "Test email from CRM Wala",
                 "<p>Your company email is connected. Your team's emails will now go out from this account.</p>")
    except RuntimeError as e:
        db.session.commit()
        raise ApiError(502, "delivery_failed", str(e)) from e
    db.session.commit()
    return ok({"sent_to": g.user.email})


@bp.delete("")
@protect("emails.read")
def disconnect():
    _owner_only()
    i = svc.get(g.workspace.id)
    if i is not None:
        i.status, i.credentials_enc, i.last_error, i.account_label, i.config = "not_connected", None, None, None, {}
        audit.record("integration.disconnected", entity_type="integration", entity_id=i.id, summary="Disconnected company email")
        db.session.commit()
    return ok(svc.view(i))
