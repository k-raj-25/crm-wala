"""Super Admin: user and workspace management with strict confirmation + audit on every destructive action."""
from __future__ import annotations

import datetime as dt
import uuid

from flask import Blueprint, current_app, g, request
from pydantic import Field
from sqlalchemy import func, or_

from app.admin_api.auth import admin_required
from app.core import crypto
from app.core.crud import MAX_PER_PAGE
from app.core.errors import ApiError, conflict, not_found
from app.core.responses import ok
from app.extensions import db
from app.models import (
    Company, Contact, Deal, ImpersonationGrant, Integration, Invoice, Lead, Payment, Plan, Subscription, User, UserSession, Workspace, WorkspaceMember,
)
from app.models.base import utcnow
from app.schemas.common import Schema, parse
from app.services import accounts as account_service
from app.services import audit
from app.services import email as email_service
from app.services.access import compute_access
from app.services.features import plan_limits
from app.services.usage import LABELS, current_usage

bp = Blueprint("admin_accounts", __name__, url_prefix="/admin-api/v1")


def _page():
    return max(int(request.args.get("page", 1)), 1), min(int(request.args.get("per_page", 25)), MAX_PER_PAGE)


def _meta(total, page, per):
    return {"page": page, "per_page": per, "total": total, "pages": max((total + per - 1) // per, 1)}


def _ws_status(ws: Workspace) -> str:
    a = compute_access(ws)
    if a.state == "suspended":
        return "suspended"
    if ws.subscription_status == "trialing":
        return "trial" if a.allowed else "trial_expired"
    return ws.subscription_status


class Confirm(Schema):
    confirm: bool = False
    confirm_text: str | None = None
    reason: str | None = Field(default=None, max_length=300)


def _need_confirm(d: Confirm, expected_text: str | None = None, reason: bool = False):
    if not d.confirm:
        raise ApiError(422, "confirmation_required", "This action needs explicit confirmation.", {"confirm": "Required"})
    if expected_text is not None and (d.confirm_text or "").strip().lower() != expected_text.lower():
        raise ApiError(422, "confirmation_required", f"Type “{expected_text}” to confirm.", {"confirm_text": "Doesn't match"})
    if reason and not (d.reason or "").strip():
        raise ApiError(422, "reason_required", "A reason is required and is stored in the audit log.", {"reason": "Required"})


# ---- users -------------------------------------------------------------------------------

def _user_row(u: User, ws_by_owner: dict) -> dict:
    ws = ws_by_owner.get(u.id)
    return {"id": str(u.id), "name": u.name, "email": u.email, "status": u.status, "created_at": u.created_at.isoformat(), "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "email_verified": bool(u.email_verified_at), "mfa_enabled": u.totp_enabled, "company": ws.name if ws else None, "workspace_id": str(ws.id) if ws else None,
            "plan": ws.plan_key if ws else None, "subscription_status": ws.subscription_status if ws else None, "trial_status": _ws_status(ws) if ws else None,
            "trial_ends_at": ws.trial_ends_at.isoformat() if ws and ws.trial_ends_at else None}


@bp.get("/users")
@admin_required()
def users():
    a = request.args
    q = db.session.query(User).filter(User.deleted_at.is_(None))
    if a.get("q"):
        like = f"%{a['q']}%"
        member_ws = db.session.query(WorkspaceMember.user_id).join(Workspace, Workspace.id == WorkspaceMember.workspace_id).filter(Workspace.name.ilike(like))
        q = q.filter(or_(User.name.ilike(like), User.email.ilike(like), User.id.in_(member_ws)))
    if a.get("status"):
        q = q.filter(User.status == a["status"])
    if a.get("plan") or a.get("subscription_status"):
        sub = db.session.query(Workspace.owner_id).filter(Workspace.deleted_at.is_(None))
        if a.get("plan"):
            sub = sub.filter(Workspace.plan_key == a["plan"])
        if a.get("subscription_status"):
            sub = sub.filter(Workspace.subscription_status == a["subscription_status"])
        q = q.filter(User.id.in_(sub))
    sort = {"created_at": User.created_at, "last_login_at": User.last_login_at, "name": User.name}.get(a.get("sort", "created_at"), User.created_at)
    page, per = _page()
    total = q.count()
    rows = q.order_by(sort.desc().nulls_last()).limit(per).offset((page - 1) * per).all()
    ws_by_owner = {}
    if rows:
        for w in db.session.query(Workspace).filter(Workspace.owner_id.in_([u.id for u in rows]), Workspace.deleted_at.is_(None)).order_by(Workspace.created_at.desc()):
            ws_by_owner[w.owner_id] = w
    return ok([_user_row(u, ws_by_owner) for u in rows], _meta(total, page, per))


@bp.get("/users/<uuid:uid>")
@admin_required()
def user_detail(uid):
    u = db.session.get(User, uid)
    if u is None or u.deleted_at:
        raise not_found("User")
    mem = db.session.query(WorkspaceMember, Workspace).join(Workspace, Workspace.id == WorkspaceMember.workspace_id).filter(WorkspaceMember.user_id == uid, Workspace.deleted_at.is_(None)).all()
    sessions = db.session.query(UserSession).filter(UserSession.user_id == uid, UserSession.revoked_at.is_(None), UserSession.expires_at > utcnow()).count()
    from app.models import AuditLog

    logs = db.session.query(AuditLog).filter(AuditLog.actor_id == uid).order_by(AuditLog.created_at.desc()).limit(15).all()
    return ok({**u.to_dict(), "email_verified": bool(u.email_verified_at), "mfa_enabled": u.totp_enabled, "active_sessions": sessions, "last_login_ip": u.last_login_ip,
               "workspaces": [{"id": str(w.id), "name": w.name, "role": m.role.name, "plan": w.plan_key, "status": _ws_status(w), "is_owner": w.owner_id == uid} for m, w in mem],
               "recent_activity": [{"time": l.created_at.isoformat(), "action": l.action, "summary": l.summary} for l in logs]})


@bp.post("/users/<uuid:uid>/suspend")
@admin_required("support")
def suspend_user(uid):
    d = parse(Confirm)
    _need_confirm(d, reason=True)
    u = db.session.get(User, uid)
    if u is None or u.deleted_at:
        raise not_found("User")
    u.status, u.suspended_reason = "suspended", d.reason
    db.session.query(UserSession).filter_by(user_id=uid, revoked_at=None).update({"revoked_at": utcnow()})
    audit.record("admin.user_suspended", entity_type="user", entity_id=uid, summary=f"Suspended {u.email}. Reason: {d.reason}", before={"status": "active"}, after={"status": "suspended"})
    db.session.commit()
    return ok({"status": u.status})


@bp.post("/users/<uuid:uid>/reactivate")
@admin_required("support")
def reactivate_user(uid):
    u = db.session.get(User, uid)
    if u is None or u.deleted_at:
        raise not_found("User")
    u.status, u.suspended_reason, u.locked_until, u.failed_login_count = "active", None, None, 0
    audit.record("admin.user_reactivated", entity_type="user", entity_id=uid, summary=f"Reactivated {u.email}")
    db.session.commit()
    return ok({"status": u.status})


@bp.post("/users/<uuid:uid>/request-password-reset")
@admin_required("support")
def request_reset(uid):
    u = db.session.get(User, uid)
    if u is None or u.deleted_at:
        raise not_found("User")
    token = account_service.signed_token("reset", str(u.id), 60, pwf=account_service.password_fingerprint(u))
    email_service.send_template("password_reset", u.email, {"name": u.name, "reset_url": f"{current_app.config['WEB_ORIGIN']}/reset-password?token={token}"})
    audit.record("admin.password_reset_requested", entity_type="user", entity_id=uid, summary=f"Sent password reset email to {u.email}")
    db.session.commit()
    return ok({"sent": True})


@bp.delete("/users/<uuid:uid>")
@admin_required("superadmin", recent_mfa=True)
def delete_user(uid):
    d = parse(Confirm)
    u = db.session.get(User, uid)
    if u is None or u.deleted_at:
        raise not_found("User")
    _need_confirm(d, expected_text=u.email, reason=True)
    owned = db.session.query(Workspace).filter(Workspace.owner_id == uid, Workspace.deleted_at.is_(None)).all()
    for w in owned:
        others = db.session.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == w.id, WorkspaceMember.user_id != uid).count()
        if others:
            raise conflict(f"“{w.name}” has {others} other member(s). Transfer or delete the workspace first.", "workspace_has_members")
    snapshot = {"email": u.email, "name": u.name}
    for w in owned:
        w.deleted_at = utcnow()
    u.deleted_at, u.status = utcnow(), "suspended"
    u.email = f"deleted+{u.id.hex[:12]}@deleted.invalid"  # frees the address; row kept for audit integrity
    db.session.query(UserSession).filter_by(user_id=uid, revoked_at=None).update({"revoked_at": utcnow()})
    audit.record("admin.user_deleted", entity_type="user", entity_id=uid, summary=f"Deleted account {snapshot['email']}. Reason: {d.reason}", before=snapshot)
    db.session.commit()
    return ok({"deleted": True})


class ImpersonateIn(Confirm):
    workspace_id: uuid.UUID


@bp.post("/users/<uuid:uid>/impersonate")
@admin_required("superadmin", "support", recent_mfa=True)
def impersonate(uid):
    d = parse(ImpersonateIn)
    u = db.session.get(User, uid)
    if u is None or u.deleted_at or u.status != "active":
        raise not_found("Active user")
    _need_confirm(d, reason=True)
    m = db.session.query(WorkspaceMember).filter_by(user_id=uid, workspace_id=d.workspace_id, status="active").one_or_none()
    if m is None:
        raise ApiError(422, "validation_error", "That user isn't an active member of that workspace", {"workspace_id": "Not a member"})
    code = crypto.random_token(32)
    db.session.add(ImpersonationGrant(admin_id=g.admin.id, user_id=uid, workspace_id=d.workspace_id, code_hash=crypto.sha256(code), reason=d.reason, expires_at=utcnow() + dt.timedelta(minutes=2)))
    audit.record("admin.impersonation_granted", entity_type="user", entity_id=uid, workspace_id=d.workspace_id, summary=f"{g.admin.email} requested impersonation of {u.email}. Reason: {d.reason}")
    db.session.commit()
    return ok({"url": f"{current_app.config['WEB_ORIGIN']}/impersonate?code={code}", "expires_in": 120})


# ---- workspaces --------------------------------------------------------------------------

def _counts(ids: list) -> dict:
    out: dict = {i: {"contacts": 0, "leads": 0, "deals": 0, "users": 0, "last_activity": None} for i in ids}
    for model, key in ((Contact, "contacts"), (Lead, "leads"), (Deal, "deals")):
        for wid, n in db.session.query(model.workspace_id, func.count()).filter(model.workspace_id.in_(ids), model.deleted_at.is_(None)).group_by(model.workspace_id):
            out[wid][key] = n
    for wid, n in db.session.query(WorkspaceMember.workspace_id, func.count()).filter(WorkspaceMember.workspace_id.in_(ids)).group_by(WorkspaceMember.workspace_id):
        out[wid]["users"] = n
    return out


def _mrr_for(ids: list) -> dict:
    out: dict = {}
    for s in db.session.query(Subscription).filter(Subscription.workspace_id.in_(ids), Subscription.status.in_(("active", "past_due"))):
        out[s.workspace_id] = out.get(s.workspace_id, 0) + (s.amount // 12 if s.interval == "annual" else s.amount)
    return out


@bp.get("/workspaces")
@admin_required()
def workspaces():
    a = request.args
    q = db.session.query(Workspace).filter(Workspace.deleted_at.is_(None))
    if a.get("q"):
        like = f"%{a['q']}%"
        q = q.filter(or_(Workspace.name.ilike(like), Workspace.slug.ilike(like), Workspace.owner_id.in_(db.session.query(User.id).filter(or_(User.email.ilike(like), User.name.ilike(like))))))
    if a.get("plan"):
        q = q.filter(Workspace.plan_key == a["plan"])
    if a.get("status"):
        st = a["status"]
        if st == "suspended":
            q = q.filter(Workspace.status == "suspended")
        elif st == "trial":
            q = q.filter(Workspace.subscription_status == "trialing", Workspace.trial_ends_at > utcnow())
        elif st == "trial_expired":
            q = q.filter(or_(Workspace.subscription_status == "expired", and_(Workspace.subscription_status == "trialing", Workspace.trial_ends_at <= utcnow())))
        else:
            q = q.filter(Workspace.subscription_status == st)
    sort = {"created_at": Workspace.created_at, "name": Workspace.name, "last_activity": Workspace.last_activity_at}.get(a.get("sort", "created_at"), Workspace.created_at)
    page, per = _page()
    total = q.count()
    rows = q.order_by(sort.desc().nulls_last()).limit(per).offset((page - 1) * per).all()
    ids = [w.id for w in rows]
    counts, mrr = (_counts(ids), _mrr_for(ids)) if ids else ({}, {})
    owners = {u.id: u for u in db.session.query(User).filter(User.id.in_([w.owner_id for w in rows]))} if rows else {}
    from app.models import UserActivityDay

    last = {wid: d for wid, d in db.session.query(UserActivityDay.workspace_id, func.max(UserActivityDay.day)).filter(UserActivityDay.workspace_id.in_(ids)).group_by(UserActivityDay.workspace_id)} if ids else {}
    return ok([{"id": str(w.id), "name": w.name, "owner": {"id": str(w.owner_id), "name": owners[w.owner_id].name, "email": owners[w.owner_id].email} if w.owner_id in owners else None,
                "users": counts[w.id]["users"], "plan": w.plan_key, "mrr": mrr.get(w.id, 0) / 100, "created_at": w.created_at.isoformat(), "status": _ws_status(w),
                "trial_ends_at": w.trial_ends_at.isoformat() if w.trial_ends_at else None, "last_activity": last[w.id].isoformat() if w.id in last else None,
                "contacts": counts[w.id]["contacts"], "leads": counts[w.id]["leads"], "deals": counts[w.id]["deals"], "is_demo": w.is_demo} for w in rows], _meta(total, page, per))


def _ws(wid) -> Workspace:
    w = db.session.get(Workspace, wid)
    if w is None or w.deleted_at:
        raise not_found("Workspace")
    return w


@bp.get("/workspaces/<uuid:wid>")
@admin_required()
def workspace_detail(wid):
    w = _ws(wid)
    counts = _counts([wid])[wid]
    usage, limits = current_usage(w), plan_limits(w)
    subs = db.session.query(Subscription).filter_by(workspace_id=wid).order_by(Subscription.created_at.desc()).limit(10).all()
    pays = db.session.query(Payment).filter_by(workspace_id=wid).order_by(Payment.created_at.desc()).limit(20).all()
    invs = db.session.query(Invoice).filter_by(workspace_id=wid).order_by(Invoice.created_at.desc()).limit(20).all()
    members = db.session.query(WorkspaceMember).filter_by(workspace_id=wid).all()
    return ok({
        **w.to_dict(exclude=("settings",)), "status_label": _ws_status(w), "access": compute_access(w).to_dict(), "counts": counts,
        "usage": [{"key": k, "label": LABELS[k], "used": usage.get(k, 0), "limit": limits.get(k)} for k in LABELS], "limit_overrides": w.limit_overrides,
        "members": [{"user_id": str(m.user_id), "name": m.user.name, "email": m.user.email, "role": m.role.name, "status": m.status} for m in members],
        "subscriptions": [s.to_dict() for s in subs], "payments": [p.to_dict() for p in pays], "invoices": [i.to_dict() for i in invs],
        "integrations": [{"provider": i.provider, "status": i.status, "mode": i.mode} for i in db.session.query(Integration).filter_by(workspace_id=wid)],
    })


class ExtendTrial(Schema):
    days: int = Field(ge=1, le=90)
    reason: str | None = Field(default=None, max_length=300)


@bp.post("/workspaces/<uuid:wid>/extend-trial")
@admin_required("support", "finance")
def extend_trial(wid):
    d = parse(ExtendTrial)
    w = _ws(wid)
    before = {"trial_ends_at": w.trial_ends_at, "status": w.subscription_status}
    base = max(w.trial_ends_at or utcnow(), utcnow())
    w.trial_ends_at = base + dt.timedelta(days=d.days)
    if w.subscription_status in ("expired", "trialing"):
        w.subscription_status, w.plan_key = "trialing", "trial"
        w.trial_milestones_sent = []
    audit.record("admin.trial_extended", entity_type="workspace", entity_id=wid, workspace_id=wid, summary=f"Extended trial by {d.days} day(s). {d.reason or ''}".strip(), before=before,
                 after={"trial_ends_at": w.trial_ends_at, "status": w.subscription_status})
    db.session.commit()
    return ok({"trial_ends_at": w.trial_ends_at.isoformat(), "status": _ws_status(w)})


@bp.post("/workspaces/<uuid:wid>/suspend")
@admin_required("superadmin", "support")
def suspend_workspace(wid):
    d = parse(Confirm)
    _need_confirm(d, reason=True)
    w = _ws(wid)
    w.status = "suspended"
    audit.record("admin.workspace_suspended", entity_type="workspace", entity_id=wid, workspace_id=wid, summary=f"Suspended workspace “{w.name}”. Reason: {d.reason}")
    db.session.commit()
    return ok({"status": "suspended"})


@bp.post("/workspaces/<uuid:wid>/reactivate")
@admin_required("superadmin", "support")
def reactivate_workspace(wid):
    w = _ws(wid)
    w.status = "active"
    audit.record("admin.workspace_reactivated", entity_type="workspace", entity_id=wid, workspace_id=wid, summary=f"Reactivated workspace “{w.name}”")
    db.session.commit()
    return ok({"status": "active"})


class ChangePlan(Schema):
    plan_key: str
    interval: str = Field(default="monthly", pattern="^(monthly|annual)$")
    period_days: int | None = Field(default=None, ge=1, le=3650)
    reason: str | None = Field(default=None, max_length=300)


@bp.post("/workspaces/<uuid:wid>/change-plan")
@admin_required("superadmin", "finance")
def change_plan(wid):
    """Complimentary plan assignment (no charge). Real purchases go through checkout."""
    d = parse(ChangePlan)
    w = _ws(wid)
    plan = db.session.query(Plan).filter_by(key=d.plan_key).one_or_none()
    if plan is None:
        raise not_found("Plan")
    before = {"plan": w.plan_key, "status": w.subscription_status}
    now = utcnow()
    if plan.is_trial:
        w.plan_key, w.subscription_status = "trial", "trialing"
        w.trial_ends_at = w.trial_ends_at if w.trial_ends_at and w.trial_ends_at > now else now + dt.timedelta(days=3)
    else:
        w.plan_key, w.billing_interval, w.subscription_status = plan.key, d.interval, "active"
        w.current_period_end = now + dt.timedelta(days=d.period_days or (365 if d.interval == "annual" else 30))
        w.grace_ends_at, w.cancel_at_period_end = None, False
        sub = db.session.query(Subscription).filter(Subscription.workspace_id == wid, Subscription.status.in_(("active", "past_due"))).first()
        if sub is None:
            sub = Subscription(workspace_id=wid, plan_key=plan.key, interval=d.interval, status="active", amount=0, currency=plan.currency, provider="admin", current_period_start=now)
            db.session.add(sub)
        sub.plan_key, sub.interval, sub.current_period_end, sub.status = plan.key, d.interval, w.current_period_end, "active"
    audit.record("admin.plan_changed", entity_type="workspace", entity_id=wid, workspace_id=wid, summary=f"Changed plan to {plan.name}. {d.reason or ''}".strip(), before=before,
                 after={"plan": w.plan_key, "status": w.subscription_status})
    db.session.commit()
    return ok({"plan_key": w.plan_key, "status": _ws_status(w)})


class Overrides(Schema):
    limits: dict[str, int | None]


@bp.put("/workspaces/<uuid:wid>/limits")
@admin_required("superadmin", "finance")
def set_limits(wid):
    d = parse(Overrides)
    w = _ws(wid)
    bad = [k for k in d.limits if k not in LABELS]
    if bad:
        raise ApiError(422, "validation_error", f"Unknown limit keys: {', '.join(bad)}", {"limits": "Unknown"})
    before = dict(w.limit_overrides or {})
    w.limit_overrides = {k: v for k, v in d.limits.items()}
    audit.record("admin.limits_changed", entity_type="workspace", entity_id=wid, workspace_id=wid, summary="Changed workspace limit overrides", before=before, after=w.limit_overrides)
    db.session.commit()
    return ok({"limit_overrides": w.limit_overrides})


class Credit(Schema):
    amount: int = Field(ge=-100000000, le=100000000, description="minor units; negative removes credit")
    reason: str = Field(min_length=1, max_length=300)


@bp.post("/workspaces/<uuid:wid>/credit")
@admin_required("superadmin", "finance")
def give_credit(wid):
    d = parse(Credit)
    w = _ws(wid)
    before = w.credit_balance
    w.credit_balance = max((w.credit_balance or 0) + d.amount, 0)
    audit.record("admin.credit_adjusted", entity_type="workspace", entity_id=wid, workspace_id=wid, summary=f"Adjusted account credit by {d.amount / 100:,.2f}. {d.reason}", before={"credit": before}, after={"credit": w.credit_balance})
    db.session.commit()
    return ok({"credit_balance": w.credit_balance})


class ExtendSub(Schema):
    days: int = Field(ge=1, le=365)
    reason: str | None = Field(default=None, max_length=300)


@bp.post("/workspaces/<uuid:wid>/extend-subscription")
@admin_required("superadmin", "finance")
def extend_subscription(wid):
    d = parse(ExtendSub)
    w = _ws(wid)
    sub = db.session.query(Subscription).filter(Subscription.workspace_id == wid, Subscription.status.in_(("active", "past_due"))).first()
    if sub is None or not w.current_period_end:
        raise conflict("This workspace has no active subscription to extend", "no_subscription")
    w.current_period_end = sub.current_period_end = w.current_period_end + dt.timedelta(days=d.days)
    if w.subscription_status == "past_due":
        w.grace_ends_at = w.grace_ends_at and w.grace_ends_at + dt.timedelta(days=d.days)
    audit.record("admin.subscription_extended", entity_type="workspace", entity_id=wid, workspace_id=wid, summary=f"Extended subscription by {d.days} day(s). {d.reason or ''}".strip())
    db.session.commit()
    return ok({"current_period_end": w.current_period_end.isoformat()})


@bp.delete("/workspaces/<uuid:wid>")
@admin_required("superadmin", recent_mfa=True)
def delete_workspace(wid):
    d = parse(Confirm)
    w = _ws(wid)
    _need_confirm(d, expected_text=w.name, reason=True)
    w.deleted_at, w.status = utcnow(), "suspended"  # soft delete: data retained until an operator purges after the recovery window
    db.session.query(UserSession).filter_by(workspace_id=wid, revoked_at=None).update({"revoked_at": utcnow()})
    audit.record("admin.workspace_deleted", entity_type="workspace", entity_id=wid, workspace_id=wid, summary=f"Deleted workspace “{w.name}”. Reason: {d.reason}")
    db.session.commit()
    return ok({"deleted": True})
