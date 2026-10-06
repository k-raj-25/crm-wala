from __future__ import annotations

import datetime as dt
import uuid
from urllib.parse import urlencode

import httpx
import jwt
import pyotp
from flask import Blueprint, current_app, g, jsonify, make_response, redirect, request
from pydantic import Field, field_validator

from app.core import crypto
from app.core.auth import (
    attach_cookies, clear_auth_cookies, encode_access, protect, start_session,
)
from app.core.errors import ApiError, bad_request, forbidden, not_found, unauthorized
from app.core.passwords import hash_password, password_problems, verify_password
from app.core.responses import ok
from app.core.tenant import bypass_scope, set_tenant
from app.extensions import db, limiter
from app.models import (
    ImpersonationGrant, Invitation, User, UserSession, Workspace, WorkspaceMember,
)
from app.models.base import utcnow
from app.schemas.common import Email, Schema, parse
from app.services import accounts, analytics, audit
from app.services import email as email_service
from app.services import settings as platform_settings
from app.services import workspaces as ws_service

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def _check_password(pw: str) -> str:
    problems = password_problems(pw)
    if problems:
        raise ValueError("Password needs " + " and ".join(problems))
    return pw


class SignupIn(Schema):
    name: str = Field(min_length=1, max_length=160)
    email: Email
    password: str
    company_name: str = Field(min_length=1, max_length=160)
    company_size: str | None = None
    industry: str | None = None
    role: str | None = Field(default=None, max_length=120)

    _pw = field_validator("password")(_check_password)


class LoginIn(Schema):
    email: Email
    password: str


class TwoFactorLoginIn(Schema):
    mfa_token: str
    code: str


def _respond_with_session(user: User, workspace_id, status: int = 200, **extra):
    session, raw = start_session(user, workspace_id)
    user.last_login_at, user.last_login_ip = utcnow(), request.remote_addr
    db.session.commit()
    # Build /me payload with the new identity
    g.user, g.session, g.impersonator_id = user, session, None
    g.workspace = db.session.get(Workspace, workspace_id) if workspace_id else None
    g.member, g.permissions, g.features = None, set(), set()
    if g.workspace is not None:
        set_tenant(g.workspace.id)
        g.member = db.session.query(WorkspaceMember).filter_by(workspace_id=workspace_id, user_id=user.id).one()
        g.permissions = set(g.member.role.permissions)
    body = {"data": {**accounts.build_me(), **extra}}
    resp = make_response(jsonify(body), status)
    return attach_cookies(resp, user, session, raw)


def _pick_workspace(user: User):
    last = (user.preferences or {}).get("last_workspace_id")
    ms = accounts.memberships_for(user)
    if not ms:
        return None
    chosen = next((m for m in ms if m["workspace_id"] == last), ms[0])
    return uuid.UUID(chosen["workspace_id"])


@bp.get("/config")
def config():
    cfg = current_app.config
    return ok({
        "google_enabled": bool(cfg["GOOGLE_CLIENT_ID"]), "signups_enabled": bool(platform_settings.get_setting("signups_enabled", default=True)),
        "require_email_verification": cfg["REQUIRE_EMAIL_VERIFICATION"], "trial_days": platform_settings.trial_days(),
        "dev_mode": cfg["ENV"] != "production",
    })


@bp.post("/signup")
@limiter.limit("10 per hour")
def signup():
    if not platform_settings.get_setting("signups_enabled", default=True):
        raise ApiError(403, "signups_disabled", "New signups are temporarily disabled.")
    data = parse(SignupIn)
    email = accounts.normalize_email(data.email)
    with bypass_scope():
        if db.session.query(User).filter(User.email == email, User.deleted_at.is_(None)).first():
            raise ApiError(409, "email_taken", "An account with this email already exists. Try signing in.", {"email": "Already registered"})
        user = User(email=email, name=data.name, password_hash=hash_password(data.password), job_role=data.role)
        db.session.add(user)
        db.session.flush()
        ws = ws_service.create_workspace(user, data.company_name, company_size=data.company_size, industry=data.industry)
        audit.record("user.signup", entity_type="user", entity_id=user.id, summary=f"{user.email} signed up",
                     workspace_id=ws.id, actor_type="user", actor_id=user.id, actor_label=user.name)
        analytics.track("signup", {"industry": data.industry}, workspace_id=ws.id, user_id=user.id)
        accounts.auth_event("signup", email=email, subject_id=user.id)
        user.preferences = {"last_workspace_id": str(ws.id)}
        verify = accounts.signed_token("verify", str(user.id), 60 * 24)
        email_service.send_template("verify_email", user.email, {"name": user.name, "verify_url": f"{current_app.config['WEB_ORIGIN']}/verify-email?token={verify}"}, workspace_id=ws.id)
        email_service.send_template("welcome", user.email, {"name": user.name, "workspace": ws.name}, workspace_id=ws.id)
        email_service.send_template("trial_started", user.email, {"name": user.name, "workspace": ws.name, "trial_ends": ws.trial_ends_at.strftime("%d %b %Y, %I:%M %p UTC")}, workspace_id=ws.id)
        ws_id = ws.id
    return _respond_with_session(user, ws_id, 201, dev_verify_token=verify if current_app.config["ENV"] != "production" else None)


def _lock_check(user: User | None) -> None:
    if user and user.locked_until and user.locked_until > utcnow():
        mins = max(int((user.locked_until - utcnow()).total_seconds() // 60) + 1, 1)
        raise ApiError(423, "account_locked", f"Too many failed attempts. Try again in {mins} minute(s) or reset your password.")


@bp.post("/login")
@limiter.limit("20 per minute")
def login():
    data = parse(LoginIn)
    email = accounts.normalize_email(data.email)
    with bypass_scope():
        user = db.session.query(User).filter(User.email == email, User.deleted_at.is_(None)).one_or_none()
        _lock_check(user)
        valid = verify_password(user.password_hash if user else None, data.password)
        if not valid:
            if user:
                user.failed_login_count += 1
                if user.failed_login_count >= current_app.config["MAX_FAILED_LOGINS"]:
                    user.locked_until = utcnow() + dt.timedelta(minutes=current_app.config["LOCKOUT_MINUTES"])
                    user.failed_login_count = 0
                    accounts.auth_event("lockout", email=email, subject_id=user.id)
            accounts.auth_event("login_failed", email=email, subject_id=user.id if user else None)
            db.session.commit()
            raise unauthorized("Incorrect email or password", "invalid_credentials")
        if user.status != "active":
            raise ApiError(403, "account_suspended", "This account has been suspended. Contact support.")
        user.failed_login_count = 0
        if user.totp_enabled:
            accounts.auth_event("mfa_challenge", email=email, subject_id=user.id)
            db.session.commit()
            return ok({"mfa_required": True, "mfa_token": accounts.signed_token("mfa", str(user.id), 5)})
        accounts.auth_event("login_success", email=email, subject_id=user.id)
        wid = _pick_workspace(user)
        return _respond_with_session(user, wid)


@bp.post("/login/2fa")
@limiter.limit("10 per minute")
def login_2fa():
    data = parse(TwoFactorLoginIn)
    try:
        claims = accounts.read_token(data.mfa_token, "mfa")
    except jwt.InvalidTokenError:
        raise unauthorized("Your sign-in expired. Please start again.", "mfa_expired")
    with bypass_scope():
        user = db.session.get(User, uuid.UUID(claims["sub"]))
        _lock_check(user)
        if user is None or not user.totp_enabled or not pyotp.TOTP(crypto.decrypt(user.totp_secret_enc)).verify(data.code.strip(), valid_window=1):
            if user:
                user.failed_login_count += 1
                if user.failed_login_count >= current_app.config["MAX_FAILED_LOGINS"]:
                    user.locked_until = utcnow() + dt.timedelta(minutes=current_app.config["LOCKOUT_MINUTES"])
                    user.failed_login_count = 0
                accounts.auth_event("2fa_failed", email=user.email, subject_id=user.id)
                db.session.commit()
            raise unauthorized("That code didn't work. Try again.", "invalid_2fa")
        accounts.auth_event("login_success", email=user.email, subject_id=user.id)
        return _respond_with_session(user, _pick_workspace(user))


@bp.post("/refresh")
@limiter.limit("60 per minute")
def refresh():
    raw = request.cookies.get("crm_refresh")
    if not raw:
        raise unauthorized("Session expired", "session_expired")
    with bypass_scope():
        old = db.session.query(UserSession).filter_by(token_hash=crypto.sha256(raw)).one_or_none()
        if old is None:
            raise unauthorized("Session expired", "session_expired")
        if old.revoked_at is not None:
            # Refresh-token reuse => assume theft, kill the whole token family.
            db.session.query(UserSession).filter_by(family_id=old.family_id, revoked_at=None).update({"revoked_at": utcnow()})
            accounts.auth_event("refresh_reuse_detected", subject_id=old.user_id)
            db.session.commit()
            raise unauthorized("Session expired", "session_expired")
        if old.expires_at <= utcnow():
            raise unauthorized("Session expired", "session_expired")
        user = db.session.get(User, old.user_id)
        if user is None or user.status != "active" or user.deleted_at is not None:
            raise unauthorized("Session expired", "session_expired")
        old.revoked_at = utcnow()
        new, new_raw = start_session(user, old.workspace_id, impersonator_id=old.impersonator_admin_id, family_id=old.family_id,
                                     ttl_days=(old.expires_at - utcnow()).total_seconds() / 86400)
        db.session.commit()
        resp = make_response(jsonify({"data": {"refreshed": True}}))
        return attach_cookies(resp, user, new, new_raw)


@bp.post("/logout")
def logout():
    raw = request.cookies.get("crm_refresh")
    with bypass_scope():
        if raw:
            s = db.session.query(UserSession).filter_by(token_hash=crypto.sha256(raw)).one_or_none()
            if s and s.revoked_at is None:
                s.revoked_at = utcnow()
                accounts.auth_event("logout", subject_id=s.user_id)
                db.session.commit()
    return clear_auth_cookies(make_response(jsonify({"data": {"ok": True}})))


@bp.get("/me")
@protect(workspace=False)
def me():
    return ok(accounts.build_me())


@bp.post("/switch-workspace")
@protect(workspace=False)
def switch_workspace():
    class In(Schema):
        workspace_id: uuid.UUID

    data = parse(In)
    member = db.session.query(WorkspaceMember).filter_by(workspace_id=data.workspace_id, user_id=g.user.id, status="active").one_or_none()
    if member is None:
        raise forbidden("You're not a member of that workspace", "not_a_member")
    g.session.workspace_id = data.workspace_id
    g.user.preferences = {**(g.user.preferences or {}), "last_workspace_id": str(data.workspace_id)}
    db.session.commit()
    g.workspace = db.session.get(Workspace, data.workspace_id)
    g.member = member
    g.permissions, g.features = set(member.role.permissions), set()
    set_tenant(data.workspace_id)
    resp = make_response(jsonify({"data": accounts.build_me()}))
    resp.set_cookie("crm_access", encode_access(g.user, data.workspace_id, g.session.id, g.impersonator_id), httponly=True,
                    samesite="Lax", secure=current_app.config["COOKIE_SECURE"], max_age=current_app.config["ACCESS_TOKEN_MINUTES"] * 60,
                    domain=current_app.config["COOKIE_DOMAIN"])
    return resp


# --- Email verification & password reset -------------------------------------------------

@bp.post("/verify-email")
@limiter.limit("20 per hour")
def verify_email():
    class In(Schema):
        token: str

    data = parse(In)
    try:
        claims = accounts.read_token(data.token, "verify")
    except jwt.InvalidTokenError:
        raise bad_request("This verification link is invalid or has expired.", "invalid_token")
    with bypass_scope():
        user = db.session.get(User, uuid.UUID(claims["sub"]))
        if user is None:
            raise bad_request("This verification link is invalid or has expired.", "invalid_token")
        if not user.email_verified_at:
            user.email_verified_at = utcnow()
            accounts.auth_event("email_verified", email=user.email, subject_id=user.id)
            db.session.commit()
    return ok({"verified": True})


@bp.post("/resend-verification")
@protect(workspace=False, verified=False)
@limiter.limit("5 per hour")
def resend_verification():
    user = g.user
    if user.email_verified_at:
        return ok({"already_verified": True})
    token = accounts.signed_token("verify", str(user.id), 60 * 24)
    email_service.send_template("verify_email", user.email, {"name": user.name, "verify_url": f"{current_app.config['WEB_ORIGIN']}/verify-email?token={token}"}, workspace_id=getattr(g.workspace, "id", None))
    db.session.commit()
    return ok({"sent": True, "dev_verify_token": token if current_app.config["ENV"] != "production" else None})


@bp.post("/forgot-password")
@limiter.limit("5 per hour")
def forgot_password():
    class In(Schema):
        email: Email

    data = parse(In)
    email = accounts.normalize_email(data.email)
    token = None
    with bypass_scope():
        user = db.session.query(User).filter(User.email == email, User.deleted_at.is_(None)).one_or_none()
        if user and user.status == "active":
            token = accounts.signed_token("reset", str(user.id), 60, pwf=accounts.password_fingerprint(user))
            email_service.send_template("password_reset", user.email, {"name": user.name, "reset_url": f"{current_app.config['WEB_ORIGIN']}/reset-password?token={token}"})
            accounts.auth_event("password_reset_requested", email=email, subject_id=user.id)
            db.session.commit()
    # Same response whether or not the account exists (no user enumeration).
    return ok({"sent": True, "dev_reset_token": token if current_app.config["ENV"] != "production" else None})


@bp.post("/reset-password")
@limiter.limit("10 per hour")
def reset_password():
    class In(Schema):
        token: str
        password: str

        _pw = field_validator("password")(_check_password)

    data = parse(In)
    try:
        claims = accounts.read_token(data.token, "reset")
    except jwt.InvalidTokenError:
        raise bad_request("This reset link is invalid or has expired.", "invalid_token")
    with bypass_scope():
        user = db.session.get(User, uuid.UUID(claims["sub"]))
        if user is None or claims.get("pwf") != accounts.password_fingerprint(user):  # single-use: changes once password changes
            raise bad_request("This reset link is invalid or has already been used.", "invalid_token")
        user.password_hash = hash_password(data.password)
        user.failed_login_count, user.locked_until = 0, None
        if not user.email_verified_at:
            user.email_verified_at = utcnow()
        db.session.query(UserSession).filter_by(user_id=user.id, revoked_at=None).update({"revoked_at": utcnow()})
        accounts.auth_event("password_reset", email=user.email, subject_id=user.id)
        db.session.commit()
    return ok({"reset": True})


@bp.post("/change-password")
@protect(workspace=False)
def change_password():
    class In(Schema):
        current_password: str
        new_password: str

        _pw = field_validator("new_password")(_check_password)

    data = parse(In)
    if not verify_password(g.user.password_hash, data.current_password):
        raise ApiError(422, "validation_error", "Current password is incorrect", {"current_password": "Incorrect password"})
    g.user.password_hash = hash_password(data.new_password)
    db.session.query(UserSession).filter(UserSession.user_id == g.user.id, UserSession.id != g.session.id, UserSession.revoked_at.is_(None)).update({"revoked_at": utcnow()})
    audit.record("user.password_changed", entity_type="user", entity_id=g.user.id, summary="Password changed")
    db.session.commit()
    return ok({"changed": True})


# --- 2FA ----------------------------------------------------------------------------------

@bp.post("/2fa/setup")
@protect(workspace=False)
def twofa_setup():
    secret = pyotp.random_base32()
    g.user.totp_secret_enc = crypto.encrypt(secret)
    g.user.totp_enabled = False
    db.session.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=g.user.email, issuer_name="CRM Wala")
    return ok({"secret": secret, "otpauth_uri": uri})


@bp.post("/2fa/enable")
@protect(workspace=False)
def twofa_enable():
    class In(Schema):
        code: str

    data = parse(In)
    if not g.user.totp_secret_enc or not pyotp.TOTP(crypto.decrypt(g.user.totp_secret_enc)).verify(data.code.strip(), valid_window=1):
        raise ApiError(422, "validation_error", "That code didn't match. Try again.", {"code": "Invalid code"})
    g.user.totp_enabled = True
    audit.record("user.2fa_enabled", entity_type="user", entity_id=g.user.id, summary="Two-factor authentication enabled")
    db.session.commit()
    return ok({"enabled": True})


@bp.post("/2fa/disable")
@protect(workspace=False)
def twofa_disable():
    class In(Schema):
        password: str
        code: str

    data = parse(In)
    if not verify_password(g.user.password_hash, data.password):
        raise ApiError(422, "validation_error", "Incorrect password", {"password": "Incorrect password"})
    if not g.user.totp_enabled or not pyotp.TOTP(crypto.decrypt(g.user.totp_secret_enc)).verify(data.code.strip(), valid_window=1):
        raise ApiError(422, "validation_error", "Invalid code", {"code": "Invalid code"})
    g.user.totp_enabled, g.user.totp_secret_enc = False, None
    audit.record("user.2fa_disabled", entity_type="user", entity_id=g.user.id, summary="Two-factor authentication disabled")
    db.session.commit()
    return ok({"enabled": False})


# --- Sessions -----------------------------------------------------------------------------

@bp.get("/sessions")
@protect(workspace=False)
def list_sessions():
    rows = db.session.query(UserSession).filter(UserSession.user_id == g.user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > utcnow()).order_by(UserSession.last_used_at.desc()).all()
    return ok([{"id": str(s.id), "ip": s.ip, "user_agent": s.user_agent, "created_at": s.created_at.isoformat(),
                "current": s.id == g.session.id} for s in rows])


@bp.delete("/sessions/<uuid:sid>")
@protect(workspace=False)
def revoke_session(sid):
    s = db.session.query(UserSession).filter_by(id=sid, user_id=g.user.id).one_or_none()
    if s is None:
        raise not_found("Session")
    s.revoked_at = utcnow()
    db.session.commit()
    return ok({"revoked": True})


# --- Google OAuth -------------------------------------------------------------------------

@bp.get("/google/start")
def google_start():
    cfg = current_app.config
    if not cfg["GOOGLE_CLIENT_ID"]:
        raise ApiError(501, "google_not_configured", "Google sign-in isn't configured on this server.")
    state = accounts.signed_token("oauth_state", crypto.random_token(8), 10)
    params = {"client_id": cfg["GOOGLE_CLIENT_ID"], "redirect_uri": f"{cfg['WEB_ORIGIN']}/api/v1/auth/google/callback",
              "response_type": "code", "scope": "openid email profile", "state": state, "prompt": "select_account"}
    resp = redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))
    resp.set_cookie("oauth_state", state, max_age=600, httponly=True, samesite="Lax", secure=cfg["COOKIE_SECURE"])
    return resp


@bp.get("/google/callback")
def google_callback():
    cfg = current_app.config
    web = cfg["WEB_ORIGIN"]
    state, code = request.args.get("state", ""), request.args.get("code")
    if not code or state != request.cookies.get("oauth_state"):
        return redirect(f"{web}/login?error=oauth_state")
    try:
        accounts.read_token(state, "oauth_state")
        tok = httpx.post("https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": cfg["GOOGLE_CLIENT_ID"], "client_secret": cfg["GOOGLE_CLIENT_SECRET"],
            "redirect_uri": f"{web}/api/v1/auth/google/callback", "grant_type": "authorization_code"}, timeout=15)
        tok.raise_for_status()
        info = httpx.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {tok.json()['access_token']}"}, timeout=15)
        info.raise_for_status()
        info = info.json()
    except Exception:
        return redirect(f"{web}/login?error=oauth_failed")
    if not info.get("email") or not info.get("email_verified"):
        return redirect(f"{web}/login?error=oauth_unverified")
    email = accounts.normalize_email(info["email"])
    with bypass_scope():
        user = db.session.query(User).filter((User.google_sub == info["sub"]) | (User.email == email)).filter(User.deleted_at.is_(None)).first()
        new = user is None
        if new:
            if not platform_settings.get_setting("signups_enabled", default=True):
                return redirect(f"{web}/login?error=signups_disabled")
            user = User(email=email, name=info.get("name") or email.split("@")[0], google_sub=info["sub"], avatar_url=info.get("picture"), email_verified_at=utcnow())
            db.session.add(user)
            db.session.flush()
            ws = ws_service.create_workspace(user, f"{user.name.split(' ')[0]}'s workspace")
            user.preferences = {"last_workspace_id": str(ws.id)}
            analytics.track("signup", {"method": "google"}, workspace_id=ws.id, user_id=user.id)
        elif user.status != "active":
            return redirect(f"{web}/login?error=suspended")
        else:
            user.google_sub = user.google_sub or info["sub"]
            user.email_verified_at = user.email_verified_at or utcnow()
        accounts.auth_event("login_success", email=email, subject_id=user.id)
        wid = _pick_workspace(user)
        session, raw = start_session(user, wid)
        user.last_login_at = utcnow()
        db.session.commit()
    resp = redirect(f"{web}/onboarding" if new else f"{web}/app")
    attach_cookies(resp, user, session, raw)
    resp.delete_cookie("oauth_state")
    return resp


# --- Invitations --------------------------------------------------------------------------

def _invite(token: str) -> Invitation:
    inv = db.session.query(Invitation).filter_by(token_hash=crypto.sha256(token)).one_or_none()
    if inv is None or inv.accepted_at or inv.revoked_at or inv.expires_at <= utcnow():
        raise bad_request("This invitation is invalid or has expired.", "invalid_invitation")
    return inv


@bp.get("/invitations/<token>")
def invitation_info(token):
    with bypass_scope():
        inv = _invite(token)
        ws = db.session.get(Workspace, inv.workspace_id)
        exists = db.session.query(User.id).filter(User.email == inv.email, User.deleted_at.is_(None)).first() is not None
        return ok({"email": inv.email, "workspace": ws.name, "role": inv.role.name, "user_exists": exists})


@bp.post("/invitations/accept")
@limiter.limit("20 per hour")
def invitation_accept():
    class In(Schema):
        token: str
        name: str | None = None
        password: str | None = None

    data = parse(In)
    with bypass_scope():
        inv = _invite(data.token)
        user = db.session.query(User).filter(User.email == inv.email, User.deleted_at.is_(None)).one_or_none()
        if user is None:
            if not data.name or not data.password:
                raise ApiError(422, "validation_error", "Name and password are required", {"name": "Required", "password": "Required"})
            problems = password_problems(data.password)
            if problems:
                raise ApiError(422, "validation_error", "Password needs " + " and ".join(problems), {"password": "Too weak"})
            user = User(email=inv.email, name=data.name, password_hash=hash_password(data.password), email_verified_at=utcnow())
            db.session.add(user)
            db.session.flush()
        else:
            # Existing account: must prove ownership by being signed in as that user.
            tok = request.cookies.get("crm_access")
            try:
                from app.core.auth import decode_access
                ok_user = tok and decode_access(tok)["sub"] == str(user.id)
            except jwt.InvalidTokenError:
                ok_user = False
            if not ok_user:
                raise ApiError(401, "login_required", "Sign in to the account for this email to accept the invitation.")
        if not db.session.query(WorkspaceMember).filter_by(workspace_id=inv.workspace_id, user_id=user.id).first():
            db.session.add(WorkspaceMember(workspace_id=inv.workspace_id, user_id=user.id, role_id=inv.role_id))
        inv.accepted_at = utcnow()
        audit.record("team.invitation_accepted", entity_type="user", entity_id=user.id, summary=f"{user.email} joined the workspace",
                     workspace_id=inv.workspace_id, actor_type="user", actor_id=user.id, actor_label=user.name)
        analytics.track("invitation_accepted", workspace_id=inv.workspace_id, user_id=user.id)
        user.preferences = {**(user.preferences or {}), "last_workspace_id": str(inv.workspace_id)}
        db.session.commit()
        return _respond_with_session(user, inv.workspace_id)


# --- Impersonation (started from the Super Admin app) -------------------------------------

@bp.post("/impersonate/exchange")
@limiter.limit("20 per hour")
def impersonate_exchange():
    class In(Schema):
        code: str

    data = parse(In)
    with bypass_scope():
        grant = db.session.query(ImpersonationGrant).filter_by(code_hash=crypto.sha256(data.code)).one_or_none()
        if grant is None or grant.used_at or grant.expires_at <= utcnow():
            raise bad_request("This impersonation link is invalid or has expired.", "invalid_grant")
        grant.used_at = utcnow()
        user = db.session.get(User, grant.user_id)
        session, raw = start_session(user, grant.workspace_id, impersonator_id=grant.admin_id, ttl_days=60 / 1440)
        audit.record("admin.impersonation_started", entity_type="user", entity_id=user.id, workspace_id=grant.workspace_id,
                     summary=f"Impersonation session started for {user.email}. Reason: {grant.reason}",
                     actor_type="admin", actor_id=grant.admin_id)
        db.session.commit()
        g.impersonator_id = grant.admin_id
        g.user, g.session = user, session
        g.workspace = db.session.get(Workspace, grant.workspace_id)
        set_tenant(g.workspace.id)
        g.member = db.session.query(WorkspaceMember).filter_by(workspace_id=grant.workspace_id, user_id=user.id).one()
        g.permissions, g.features = set(g.member.role.permissions), set()
        resp = make_response(jsonify({"data": accounts.build_me()}))
        return attach_cookies(resp, user, session, raw)
