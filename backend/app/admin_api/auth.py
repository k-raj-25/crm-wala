"""Super Admin authentication. Completely independent of customer auth: separate table, secret, audience, cookies.

A customer token can never satisfy `admin_required` (different signing key + audience + subject table), and an
admin token is never accepted by the customer API.
"""
from __future__ import annotations

import datetime as dt
import functools
import uuid

import jwt
import pyotp
from flask import Blueprint, current_app, g, jsonify, make_response, request
from pydantic import Field

from app.core import crypto
from app.core.errors import ApiError, forbidden, unauthorized
from app.core.passwords import hash_password, verify_password
from app.core.responses import ok
from app.core.security import clear_cookie, set_cookie
from app.core.tenant import set_tenant
from app.extensions import db, limiter
from app.models import AdminSession, AdminUser
from app.models.base import utcnow
from app.schemas.common import Email, Schema, parse
from app.services import accounts, audit

bp = Blueprint("admin_auth", __name__, url_prefix="/admin-api/v1/auth")
ISS, AUD = "crm-wala", "crm-admin"
REFRESH_PATH = "/admin-api/v1/auth"


def _encode(admin: AdminUser, sid) -> str:
    cfg, now = current_app.config, utcnow()
    return jwt.encode({"iss": ISS, "aud": AUD, "sub": str(admin.id), "sid": str(sid), "typ": "admin_access", "iat": now,
                       "exp": now + dt.timedelta(minutes=cfg["ADMIN_ACCESS_TOKEN_MINUTES"])}, cfg["ADMIN_JWT_SECRET"], algorithm="HS256")


def _ip_allowed() -> None:
    allow = current_app.config["ADMIN_ALLOWED_IPS"]
    if allow and request.remote_addr not in allow:
        raise ApiError(403, "ip_not_allowed", "Access to the admin console isn't allowed from this network.")


def _start(admin: AdminUser, mfa: bool):
    cfg = current_app.config
    raw = crypto.random_token(48)
    s = AdminSession(admin_id=admin.id, token_hash=crypto.sha256(raw), expires_at=utcnow() + dt.timedelta(hours=cfg["ADMIN_SESSION_HOURS"]),
                     mfa_verified_at=utcnow() if mfa else None, ip=request.remote_addr, user_agent=(request.headers.get("User-Agent") or "")[:300])
    db.session.add(s)
    db.session.flush()
    admin.last_login_at, admin.last_login_ip = utcnow(), request.remote_addr
    return s, raw


def _cookies(resp, admin, s, raw):
    cfg = current_app.config
    set_cookie(resp, "adm_access", _encode(admin, s.id), max_age=cfg["ADMIN_ACCESS_TOKEN_MINUTES"] * 60)
    remaining = max(int((s.expires_at - utcnow()).total_seconds()), 60)
    set_cookie(resp, "adm_refresh", raw, max_age=remaining, path=REFRESH_PATH)
    set_cookie(resp, "adm_csrf", crypto.random_token(24), max_age=remaining, http_only=False)
    return resp


def admin_dict(a: AdminUser) -> dict:
    return {"id": str(a.id), "email": a.email, "name": a.name, "role": a.role, "mfa_enabled": a.totp_enabled, "last_login_at": a.last_login_at.isoformat() if a.last_login_at else None}


def admin_required(*roles: str, recent_mfa: bool = False):
    """Authenticate an admin. `roles` restricts to those roles (superadmin always allowed). `recent_mfa` demands a TOTP verification this session."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            _ip_allowed()
            token = request.cookies.get("adm_access") or (request.headers.get("Authorization", "")[7:] if request.headers.get("Authorization", "").startswith("Bearer ") else None)
            if not token:
                raise unauthorized("Admin authentication required", "unauthenticated")
            try:
                claims = jwt.decode(token, current_app.config["ADMIN_JWT_SECRET"], algorithms=["HS256"], audience=AUD, issuer=ISS, options={"require": ["exp", "sub", "sid"]})
            except jwt.ExpiredSignatureError:
                raise unauthorized("Session expired", "token_expired")
            except jwt.InvalidTokenError:
                raise unauthorized("Invalid session", "invalid_token")
            from app.core.tenant import set_tenant as _st

            _st(None, bypass=True)  # admin console reads across tenants
            s = db.session.get(AdminSession, uuid.UUID(claims["sid"]))
            admin = db.session.get(AdminUser, uuid.UUID(claims["sub"]))
            if s is None or s.revoked_at or s.expires_at <= utcnow() or admin is None or admin.status != "active" or s.admin_id != admin.id:
                raise unauthorized("Session ended", "session_revoked")
            if current_app.config["ADMIN_REQUIRE_2FA"] and not s.mfa_verified_at:
                raise forbidden("Two-factor authentication required", "mfa_required")
            if roles and admin.role != "superadmin" and admin.role not in roles:
                raise forbidden("Your admin role doesn't allow this action", "role_forbidden")
            if recent_mfa and (not s.mfa_verified_at or utcnow() - s.mfa_verified_at > dt.timedelta(hours=1)):
                raise ApiError(403, "mfa_recent_required", "Re-verify your authenticator code to perform this action.")
            g.admin, g.admin_session, g.user, g.workspace = admin, s, None, None
            return fn(*a, **kw)

        return wrapper

    return deco


class LoginIn(Schema):
    email: Email
    password: str


class ReverifyIn(Schema):
    code: str = Field(min_length=6, max_length=8)


class TwoFaIn(Schema):
    mfa_token: str
    code: str = Field(min_length=6, max_length=8)


def _fail(admin: AdminUser | None, email: str, event: str):
    if admin:
        admin.failed_login_count += 1
        if admin.failed_login_count >= max(current_app.config["MAX_FAILED_LOGINS"] - 2, 3):
            admin.locked_until = utcnow() + dt.timedelta(minutes=current_app.config["LOCKOUT_MINUTES"] * 2)
            admin.failed_login_count = 0
            accounts.auth_event("lockout", email=email, subject_id=admin.id, realm="admin")
    accounts.auth_event(event, email=email, subject_id=admin.id if admin else None, realm="admin")
    db.session.commit()


@bp.post("/login")
@limiter.limit("10 per minute")
def login():
    _ip_allowed()
    set_tenant(None, bypass=True)
    d = parse(LoginIn)
    email = accounts.normalize_email(d.email)
    admin = db.session.query(AdminUser).filter(AdminUser.email == email).one_or_none()
    if admin and admin.locked_until and admin.locked_until > utcnow():
        raise ApiError(423, "account_locked", "Too many failed attempts. Try again later.")
    if not verify_password(admin.password_hash if admin else None, d.password) or (admin and admin.status != "active"):
        _fail(admin, email, "login_failed")
        raise unauthorized("Incorrect email or password", "invalid_credentials")
    admin.failed_login_count = 0
    need_mfa = admin.totp_enabled or current_app.config["ADMIN_REQUIRE_2FA"]
    if need_mfa:
        token = accounts.signed_token("admin_mfa", str(admin.id), 5)
        if not admin.totp_enabled:
            secret = pyotp.random_base32()
            admin.totp_secret_enc = crypto.encrypt(secret)
            db.session.commit()
            return ok({"mfa_setup_required": True, "mfa_token": token, "secret": secret, "otpauth_uri": pyotp.TOTP(secret).provisioning_uri(admin.email, issuer_name="CRM Wala Admin")})
        db.session.commit()
        return ok({"mfa_required": True, "mfa_token": token})
    s, raw = _start(admin, mfa=False)
    accounts.auth_event("login_success", email=email, subject_id=admin.id, realm="admin")
    db.session.commit()
    return _cookies(make_response(jsonify({"data": {"admin": admin_dict(admin)}})), admin, s, raw)


@bp.post("/login/2fa")
@limiter.limit("10 per minute")
def login_2fa():
    _ip_allowed()
    set_tenant(None, bypass=True)
    d = parse(TwoFaIn)
    try:
        claims = accounts.read_token(d.mfa_token, "admin_mfa")
    except jwt.InvalidTokenError:
        raise unauthorized("Your sign-in expired. Start again.", "mfa_expired")
    admin = db.session.get(AdminUser, uuid.UUID(claims["sub"]))
    if admin is None or admin.status != "active" or not admin.totp_secret_enc or (admin.locked_until and admin.locked_until > utcnow()):
        raise unauthorized("Sign-in failed", "invalid_credentials")
    if not pyotp.TOTP(crypto.decrypt(admin.totp_secret_enc)).verify(d.code.strip(), valid_window=1):
        _fail(admin, admin.email, "2fa_failed")
        raise unauthorized("That code didn't work", "invalid_2fa")
    admin.totp_enabled = True
    s, raw = _start(admin, mfa=True)
    accounts.auth_event("login_success", email=admin.email, subject_id=admin.id, realm="admin")
    db.session.commit()
    return _cookies(make_response(jsonify({"data": {"admin": admin_dict(admin)}})), admin, s, raw)


@bp.post("/reverify")
@admin_required()
def reverify():
    """Step-up: re-enter a TOTP code before sensitive actions (impersonate, delete)."""
    d = parse(ReverifyIn)
    if not g.admin.totp_secret_enc or not pyotp.TOTP(crypto.decrypt(g.admin.totp_secret_enc)).verify(d.code.strip(), valid_window=1):
        raise unauthorized("That code didn't work", "invalid_2fa")
    g.admin_session.mfa_verified_at = utcnow()
    db.session.commit()
    return ok({"verified": True})


@bp.post("/refresh")
@limiter.limit("60 per minute")
def refresh():
    _ip_allowed()
    set_tenant(None, bypass=True)
    raw = request.cookies.get("adm_refresh")
    s = db.session.query(AdminSession).filter_by(token_hash=crypto.sha256(raw)).one_or_none() if raw else None
    if s is None or s.revoked_at or s.expires_at <= utcnow():
        raise unauthorized("Session expired", "session_expired")
    admin = db.session.get(AdminUser, s.admin_id)
    if admin is None or admin.status != "active":
        raise unauthorized("Session expired", "session_expired")
    # Admin sessions don't rotate refresh tokens (short absolute lifetime), but they do slide the access token.
    resp = make_response(jsonify({"data": {"refreshed": True}}))
    set_cookie(resp, "adm_access", _encode(admin, s.id), max_age=current_app.config["ADMIN_ACCESS_TOKEN_MINUTES"] * 60)
    return resp


@bp.post("/logout")
def logout():
    set_tenant(None, bypass=True)
    raw = request.cookies.get("adm_refresh")
    if raw:
        s = db.session.query(AdminSession).filter_by(token_hash=crypto.sha256(raw)).one_or_none()
        if s and not s.revoked_at:
            s.revoked_at = utcnow()
            db.session.commit()
    resp = make_response(jsonify({"data": {"ok": True}}))
    clear_cookie(resp, "adm_access")
    clear_cookie(resp, "adm_refresh", REFRESH_PATH)
    clear_cookie(resp, "adm_csrf")
    return resp


@bp.get("/me")
@admin_required()
def me():
    return ok({"admin": admin_dict(g.admin), "mfa_verified": bool(g.admin_session.mfa_verified_at), "config": {"require_2fa": current_app.config["ADMIN_REQUIRE_2FA"]}})
