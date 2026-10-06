"""Customer-app authentication: short-lived JWT access cookie + rotating server-side refresh sessions.

The `protect` decorator is the single choke point for authentication, tenant resolution, subscription
gating, permission checks and feature gating on every customer API route.
"""
from __future__ import annotations

import datetime as dt
import functools
import uuid
from typing import Callable

import jwt
from flask import Response, current_app, g, request

from app.core import crypto
from app.core.errors import ApiError, forbidden, unauthorized
from app.core.permissions import has_permission
from app.core.security import clear_cookie, set_cookie
from app.core.tenant import set_tenant
from app.extensions import db
from app.models import User, UserSession, Workspace, WorkspaceMember
from app.models.base import utcnow
from app.services import features as feature_service
from app.services.access import compute_access

ISS, AUD = "crm-wala", "crm-web"
REFRESH_PATH = "/api/v1/auth"


def _now() -> dt.datetime:
    return utcnow()


def encode_access(user: User, workspace_id, session_id, impersonator_id=None) -> str:
    cfg = current_app.config
    now = _now()
    payload = {
        "iss": ISS, "aud": AUD, "sub": str(user.id), "wid": str(workspace_id) if workspace_id else None, "sid": str(session_id),
        "iat": now, "exp": now + dt.timedelta(minutes=cfg["ACCESS_TOKEN_MINUTES"]), "typ": "access",
    }
    if impersonator_id:
        payload["imp"] = str(impersonator_id)
    return jwt.encode(payload, cfg["JWT_SECRET"], algorithm="HS256")


def decode_access(token: str) -> dict:
    return jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"], audience=AUD, issuer=ISS,
                      options={"require": ["exp", "sub", "sid"]})


def start_session(user: User, workspace_id, *, impersonator_id=None, family_id=None, ttl_days: float | None = None) -> tuple[UserSession, str]:
    cfg = current_app.config
    raw = crypto.random_token(48)
    days = ttl_days if ttl_days is not None else cfg["REFRESH_TOKEN_DAYS"]
    s = UserSession(
        user_id=user.id, workspace_id=workspace_id, token_hash=crypto.sha256(raw), family_id=family_id or uuid.uuid4(),
        expires_at=_now() + dt.timedelta(days=days), ip=request.remote_addr,
        user_agent=(request.headers.get("User-Agent") or "")[:300], impersonator_admin_id=impersonator_id,
    )
    db.session.add(s)
    db.session.flush()
    return s, raw


def attach_cookies(resp: Response, user: User, session: UserSession, refresh_raw: str) -> Response:
    cfg = current_app.config
    imp = session.impersonator_admin_id
    access = encode_access(user, session.workspace_id, session.id, imp)
    set_cookie(resp, "crm_access", access, max_age=cfg["ACCESS_TOKEN_MINUTES"] * 60)
    remaining = max(int((session.expires_at - _now()).total_seconds()), 60)
    set_cookie(resp, "crm_refresh", refresh_raw, max_age=remaining, path=REFRESH_PATH)
    set_cookie(resp, "crm_csrf", crypto.random_token(24), max_age=remaining, http_only=False)
    return resp


def clear_auth_cookies(resp: Response) -> Response:
    clear_cookie(resp, "crm_access")
    clear_cookie(resp, "crm_refresh", REFRESH_PATH)
    clear_cookie(resp, "crm_csrf")
    return resp


def _token_from_request() -> str | None:
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        return h[7:]
    return request.cookies.get("crm_access")


def _load_identity(require_workspace: bool) -> None:
    token = _token_from_request()
    if not token:
        raise unauthorized()
    try:
        claims = decode_access(token)
    except jwt.ExpiredSignatureError:
        raise unauthorized("Your session has expired. Please sign in again.", "token_expired")
    except jwt.InvalidTokenError:
        raise unauthorized("Invalid session", "invalid_token")
    if claims.get("typ") != "access":
        raise unauthorized("Invalid session", "invalid_token")

    sess = db.session.get(UserSession, uuid.UUID(claims["sid"]))
    if sess is None or sess.revoked_at is not None or sess.expires_at <= _now():
        raise unauthorized("Your session has ended. Please sign in again.", "session_revoked")
    user = db.session.get(User, uuid.UUID(claims["sub"]))
    if user is None or user.deleted_at is not None:
        raise unauthorized()
    if user.status != "active":
        raise ApiError(403, "account_suspended", "This account has been suspended. Contact support.")
    g.user, g.session, g.impersonator_id = user, sess, claims.get("imp")
    g.workspace = g.member = None
    g.permissions = set()
    g.features = set()

    wid = claims.get("wid")
    if wid:
        member = (
            db.session.query(WorkspaceMember).filter_by(workspace_id=uuid.UUID(wid), user_id=user.id, status="active").one_or_none()
        )
        ws = db.session.get(Workspace, uuid.UUID(wid))
        if member is None or ws is None or ws.deleted_at is not None:
            raise forbidden("You no longer have access to this workspace", "workspace_access_revoked")
        g.workspace, g.member = ws, member
        g.permissions = set(member.role.permissions)
        set_tenant(ws.id)  # activates Postgres RLS for the rest of the request
    elif require_workspace:
        raise forbidden("No active workspace", "no_workspace")
    _mark_active(user.id, wid)


def _mark_active(user_id, wid) -> None:
    """Record one active-day row per user per day (Redis guards the DB write). Best-effort."""
    from app.core import cache

    day = _now().date()
    if not cache.set_once(f"active:{user_id}:{day}", 86400):
        return
    try:
        from sqlalchemy.dialects.postgresql import insert

        from app.models import UserActivityDay

        db.session.execute(insert(UserActivityDay).values(user_id=user_id, day=day, workspace_id=uuid.UUID(wid) if wid else None).on_conflict_do_nothing())
    except Exception:  # pragma: no cover
        pass


def protect(
    perm: str | None = None, *, feature: str | None = None, allow_restricted: bool = False, workspace: bool = True,
    verified: bool = True,
) -> Callable:
    """Authenticate + resolve tenant + gate on subscription state, permission and plan feature."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            _load_identity(workspace)
            user, ws = g.user, g.workspace
            if verified and current_app.config["REQUIRE_EMAIL_VERIFICATION"] and not user.email_verified_at and workspace:
                raise ApiError(403, "email_not_verified", "Please verify your email address to continue.")
            if ws is not None:
                access = compute_access(ws)
                g.access = access
                if access.state == "suspended":
                    raise ApiError(403, "workspace_suspended", "This workspace has been suspended. Contact support.")
                if not access.allowed and not allow_restricted:
                    code = "trial_expired" if access.reason == "trial_expired" else "subscription_required"
                    msg = "Your trial has ended. Choose a plan to continue." if code == "trial_expired" else (
                        "Your subscription needs attention. Update billing to continue.")
                    raise ApiError(402, code, msg, {"reason": access.reason})
                g.features = feature_service.workspace_features(ws)
            if perm and not has_permission(g.permissions, perm):
                raise forbidden(f"Your role doesn't allow this action ({perm})", "permission_denied")
            if feature and feature not in g.features:
                raise ApiError(402, "feature_unavailable", "This feature isn't included in your current plan.", {"feature": feature})
            return fn(*args, **kwargs)

        return wrapper

    return deco


def require(perm: str) -> None:
    """Inline permission check for routes whose needed permission depends on the payload."""
    if not has_permission(g.permissions, perm):
        raise forbidden(f"Your role doesn't allow this action ({perm})", "permission_denied")
