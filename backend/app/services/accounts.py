"""Account-level helpers shared by the auth API, invitations and the admin app."""
from __future__ import annotations

import datetime as dt
import uuid

import jwt
from flask import current_app, g, request

from app.core import crypto
from app.extensions import db
from app.models import AuthEvent, Plan, User, Workspace, WorkspaceMember
from app.models.base import utcnow
from app.services import features as feature_service
from app.services.access import compute_access


def normalize_email(email: str) -> str:
    return email.strip().lower()


def auth_event(event: str, *, email: str | None = None, subject_id=None, realm: str = "user") -> None:
    db.session.add(AuthEvent(realm=realm, event=event, email=email, subject_id=subject_id, ip=request.remote_addr,
                             user_agent=(request.headers.get("User-Agent") or "")[:300]))


def signed_token(typ: str, subject: str, minutes: int, **extra) -> str:
    now = utcnow()
    return jwt.encode({"typ": typ, "sub": subject, "iat": now, "exp": now + dt.timedelta(minutes=minutes), **extra},
                      current_app.config["SECRET_KEY"], algorithm="HS256")


def read_token(token: str, typ: str) -> dict:
    claims = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"], options={"require": ["exp", "sub"]})
    if claims.get("typ") != typ:
        raise jwt.InvalidTokenError("wrong token type")
    return claims


def password_fingerprint(user: User) -> str:
    return crypto.sha256(user.password_hash or "")[:16]


def memberships_for(user: User) -> list[dict]:
    rows = (
        db.session.query(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .filter(WorkspaceMember.user_id == user.id, WorkspaceMember.status == "active", Workspace.deleted_at.is_(None))
        .order_by(Workspace.created_at)
        .all()
    )
    return [{"workspace_id": str(w.id), "name": w.name, "slug": w.slug, "role": m.role.key, "role_name": m.role.name,
             "logo_url": w.logo_url, "plan_key": w.plan_key} for m, w in rows]


def subscription_summary(ws: Workspace) -> dict:
    plan = feature_service.get_plan(ws.plan_key)
    access = compute_access(ws)
    return {
        "plan_key": ws.plan_key, "plan_name": plan.name if plan else ws.plan_key, "status": ws.subscription_status,
        "interval": ws.billing_interval, "trial_ends_at": ws.trial_ends_at.isoformat() if ws.trial_ends_at else None,
        "trial_started_at": ws.trial_started_at.isoformat() if ws.trial_started_at else None,
        "current_period_end": ws.current_period_end.isoformat() if ws.current_period_end else None,
        "grace_ends_at": ws.grace_ends_at.isoformat() if ws.grace_ends_at else None,
        "cancel_at_period_end": ws.cancel_at_period_end, "access": access.to_dict(),
    }


def build_me() -> dict:
    user: User = g.user
    ws: Workspace | None = g.workspace
    out = {
        "user": {**user.to_dict(), "email_verified": bool(user.email_verified_at), "mfa_enabled": user.totp_enabled},
        "workspaces": memberships_for(user),
        "workspace": None,
        "impersonating": bool(getattr(g, "impersonator_id", None)),
    }
    if ws is not None:
        out["workspace"] = {
            **ws.to_dict(exclude=("settings",)),
            "lead_statuses": (ws.settings or {}).get("lead_statuses", []),
            "branding": (ws.settings or {}).get("branding", {}),
        }
        out["role"] = {"key": g.member.role.key, "name": g.member.role.name}
        out["permissions"] = sorted(g.permissions)
        out["features"] = sorted(g.features) if g.features else sorted(feature_service.workspace_features(ws))
        out["limits"] = feature_service.plan_limits(ws)
        out["subscription"] = subscription_summary(ws)
    return out
