"""Super Admin: platform dashboard, product analytics, audit logs, system health, settings, feature flags, email templates."""
from __future__ import annotations

import csv
import datetime as dt
import io

from flask import Blueprint, Response, current_app, g, request
from pydantic import Field
from sqlalchemy import Date, and_, cast, func, or_, text

from app.admin_api.auth import admin_dict, admin_required
from app.core import cache
from app.core.crud import MAX_PER_PAGE, parse_date
from app.core.errors import ApiError, conflict, not_found
from app.core.passwords import hash_password, password_problems
from app.core.responses import created, ok
from app.extensions import db
from app.models import (
    AdminUser, AiUsage, AnalyticsEvent, ApiErrorLog, AuditLog, AuthEvent, Contact, Deal, EmailLog, FeatureFlag, Integration, JobLog, Lead, Payment,
    PlatformEmailTemplate, PlatformSetting, Subscription, User, UserActivityDay, WebhookEvent, Workspace,
)
from app.models.base import utcnow
from app.schemas.common import Email, Schema, parse
from app.services import audit, email as email_service

bp = Blueprint("admin_platform", __name__, url_prefix="/admin-api/v1")


def _range(default_days=30):
    end = parse_date(request.args.get("to"), end=True) or utcnow()
    start = parse_date(request.args.get("from")) or (end - dt.timedelta(days=default_days))
    return start, end


def _series(rows: dict, start, end, keys, bucket="day"):
    out, cur = [], start.replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "month":
        cur = cur.replace(day=1)
    while cur <= end:
        k = cur.date().isoformat()
        out.append({"period": k, **{c: rows.get(k, {}).get(c, 0) for c in keys}})
        cur = cur + dt.timedelta(days=1) if bucket == "day" else (cur.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return out


def mrr_cents() -> int:
    total = 0
    for sub in db.session.query(Subscription).filter(Subscription.status.in_(("active", "past_due"))).all():
        total += int(sub.amount / 12) if sub.interval == "annual" else sub.amount
    return total


@bp.get("/dashboard")
@admin_required()
def dashboard():
    start, end = _range(30)
    s = db.session
    now = utcnow()
    total_users = s.query(func.count(User.id)).filter(User.deleted_at.is_(None)).scalar()
    ws_total = s.query(func.count(Workspace.id)).filter(Workspace.deleted_at.is_(None)).scalar()
    active_ws = s.query(func.count(func.distinct(UserActivityDay.workspace_id))).filter(UserActivityDay.day >= (now - dt.timedelta(days=30)).date()).scalar()
    trials = s.query(func.count(Workspace.id)).filter(Workspace.deleted_at.is_(None), Workspace.subscription_status == "trialing", Workspace.trial_ends_at > now).scalar()
    paid = s.query(func.count(Workspace.id)).filter(Workspace.deleted_at.is_(None), Workspace.subscription_status.in_(("active", "past_due"))).scalar()
    cancelled = s.query(func.count(Subscription.id)).filter(or_(Subscription.status == "ended", Subscription.cancel_at_period_end.is_(True))).scalar()
    new_users = s.query(func.count(User.id)).filter(User.created_at >= start, User.created_at <= end, User.deleted_at.is_(None)).scalar()
    mrr = mrr_cents()
    # trial conversion: of workspaces whose trial has finished, share that became paying
    finished = s.query(func.count(Workspace.id)).filter(Workspace.trial_ends_at <= now, Workspace.is_demo.is_(False), Workspace.deleted_at.is_(None)).scalar()
    converted = s.query(func.count(func.distinct(Subscription.workspace_id))).scalar()
    cancelled_30 = s.query(func.count(Subscription.id)).filter(Subscription.ended_at >= now - dt.timedelta(days=30)).scalar()
    active_start = s.query(func.count(Subscription.id)).filter(Subscription.created_at <= now - dt.timedelta(days=30), or_(Subscription.ended_at.is_(None), Subscription.ended_at >= now - dt.timedelta(days=30))).scalar()
    users_by_day = {r[0].isoformat(): {"users": r[1]} for r in s.query(cast(User.created_at, Date), func.count()).filter(User.created_at >= start, User.created_at <= end).group_by(cast(User.created_at, Date))}
    ws_by_day = {r[0].isoformat(): {"workspaces": r[1]} for r in s.query(cast(Workspace.created_at, Date), func.count()).filter(Workspace.created_at >= start, Workspace.created_at <= end).group_by(cast(Workspace.created_at, Date))}
    user_growth = _series({k: {**users_by_day.get(k, {}), **ws_by_day.get(k, {})} for k in {*users_by_day, *ws_by_day}}, start, end, ["users", "workspaces"])
    cum = s.query(func.count(User.id)).filter(User.created_at < start).scalar()
    for r in user_growth:
        cum += r["users"]
        r["total_users"] = cum
    rev = {r[0].isoformat(): {"revenue": float(r[1] or 0) / 100} for r in s.query(cast(Payment.created_at, Date), func.sum(Payment.amount - Payment.refunded_amount)).filter(
        Payment.status.in_(("succeeded", "refunded")), Payment.created_at >= start, Payment.created_at <= end).group_by(cast(Payment.created_at, Date))}
    new_subs = {r[0].isoformat(): {"new": r[1]} for r in s.query(cast(Subscription.created_at, Date), func.count()).filter(Subscription.created_at >= start, Subscription.created_at <= end).group_by(cast(Subscription.created_at, Date))}
    canc = {r[0].isoformat(): {"cancelled": r[1]} for r in s.query(cast(Subscription.ended_at, Date), func.count()).filter(Subscription.ended_at >= start, Subscription.ended_at <= end).group_by(cast(Subscription.ended_at, Date))}
    subs_series = _series({k: {**new_subs.get(k, {}), **canc.get(k, {})} for k in {*new_subs, *canc}}, start, end, ["new", "cancelled"])
    plan_dist = [{"plan": r[0], "workspaces": r[1]} for r in s.query(Workspace.plan_key, func.count()).filter(Workspace.deleted_at.is_(None), Workspace.is_demo.is_(False)).group_by(Workspace.plan_key).order_by(func.count().desc())]
    # monthly trial cohorts for the conversion chart
    cohorts = []
    for i in range(5, -1, -1):
        a = (now.replace(day=1) - dt.timedelta(days=31 * i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        b = (a + dt.timedelta(days=32)).replace(day=1)
        created_n = s.query(func.count(Workspace.id)).filter(Workspace.created_at >= a, Workspace.created_at < b, Workspace.is_demo.is_(False)).scalar()
        conv_n = s.query(func.count(func.distinct(Subscription.workspace_id))).join(Workspace, Workspace.id == Subscription.workspace_id).filter(Workspace.created_at >= a, Workspace.created_at < b, Workspace.is_demo.is_(False)).scalar()
        cohorts.append({"period": a.date().isoformat(), "trials": created_n, "converted": conv_n, "rate": round(conv_n / created_n * 100, 1) if created_n else 0})
    return ok({
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "metrics": {"total_users": total_users, "total_workspaces": ws_total, "active_workspaces": active_ws, "trial_workspaces": trials, "paid_workspaces": paid, "cancelled_subscriptions": cancelled,
                    "mrr": mrr / 100, "arr": mrr * 12 / 100, "new_users": new_users, "churn_rate": round(cancelled_30 / active_start * 100, 1) if active_start else 0.0,
                    "trial_conversion_rate": round(converted / finished * 100, 1) if finished else 0.0},
        "charts": {"user_growth": user_growth, "revenue": _series(rev, start, end, ["revenue"]), "trial_conversion": cohorts, "subscriptions": subs_series, "plan_distribution": plan_dist},
    })


@bp.get("/analytics")
@admin_required()
def analytics():
    now, s = utcnow(), db.session
    today = now.date()
    dau = s.query(func.count(func.distinct(UserActivityDay.user_id))).filter(UserActivityDay.day == today).scalar()
    wau = s.query(func.count(func.distinct(UserActivityDay.user_id))).filter(UserActivityDay.day > today - dt.timedelta(days=7)).scalar()
    mau = s.query(func.count(func.distinct(UserActivityDay.user_id))).filter(UserActivityDay.day > today - dt.timedelta(days=30)).scalar()
    start = now - dt.timedelta(days=30)
    dau_series = {r[0].isoformat(): {"dau": r[1]} for r in s.query(UserActivityDay.day, func.count()).filter(UserActivityDay.day >= start.date()).group_by(UserActivityDay.day)}
    # feature usage = audit actions grouped by entity family, last 30 days
    usage = s.query(AuditLog.entity_type, func.count()).filter(AuditLog.created_at >= start, AuditLog.entity_type.isnot(None), AuditLog.actor_type == "user").group_by(AuditLog.entity_type).order_by(func.count().desc()).limit(12).all()
    events = s.query(AnalyticsEvent.name, func.count()).filter(AnalyticsEvent.created_at >= start).group_by(AnalyticsEvent.name).order_by(func.count().desc()).all()
    integ = s.query(Integration.provider, func.count()).filter(Integration.status == "connected").group_by(Integration.provider).order_by(func.count().desc()).all()
    actions_per_user_day = s.query(func.count(AuditLog.id)).filter(AuditLog.created_at >= start, AuditLog.actor_type == "user").scalar() or 0
    user_days = s.query(func.count()).select_from(UserActivityDay).filter(UserActivityDay.day >= start.date()).scalar() or 0

    def distinct_ws(name):
        return s.query(func.count(func.distinct(AnalyticsEvent.workspace_id))).filter(AnalyticsEvent.name == name).scalar()

    funnel_names = ["signup", "workspace_created", "onboarding_completed", "lead_created", "deal_created", "deal_won", "subscription_started"]
    funnel = [{"step": n, "count": distinct_ws(n)} for n in funnel_names]
    trial_ws = s.query(Workspace.id).filter(Workspace.subscription_status.in_(("trialing", "expired")), Workspace.is_demo.is_(False)).subquery()
    engaged = {n: s.query(func.count(func.distinct(AnalyticsEvent.workspace_id))).filter(AnalyticsEvent.name == n, AnalyticsEvent.workspace_id.in_(s.query(trial_ws.c.id))).scalar() for n in ("lead_created", "deal_created", "automation_created", "ai_chat")}
    ai = s.query(Workspace.name, func.count(AiUsage.id), func.coalesce(func.sum(AiUsage.input_tokens + AiUsage.output_tokens), 0)).join(AiUsage, AiUsage.workspace_id == Workspace.id).filter(AiUsage.created_at >= now.replace(day=1, hour=0, minute=0, second=0)).group_by(Workspace.id).order_by(func.count(AiUsage.id).desc()).limit(10).all()
    return ok({
        "active_users": {"dau": dau, "wau": wau, "mau": mau}, "dau_series": _series(dau_series, start, now, ["dau"]),
        "feature_usage": [{"feature": r[0], "actions": r[1]} for r in usage], "events": [{"name": r[0], "count": r[1]} for r in events],
        "integrations": [{"provider": r[0], "connected": r[1]} for r in integ], "avg_actions_per_active_day": round(actions_per_user_day / user_days, 1) if user_days else 0,
        "funnel": funnel, "trial_engagement": {"trial_workspaces": s.query(func.count()).select_from(trial_ws).scalar(), **engaged},
        "ai_consumption": [{"workspace": r[0], "actions": r[1], "tokens": int(r[2])} for r in ai],
    })


@bp.get("/audit-logs")
@admin_required()
def audit_logs():
    a = request.args
    q = db.session.query(AuditLog)
    if a.get("q"):
        q = q.filter(or_(AuditLog.summary.ilike(f"%{a['q']}%"), AuditLog.actor_label.ilike(f"%{a['q']}%"), AuditLog.action.ilike(f"%{a['q']}%")))
    for param, col in (("action", AuditLog.action), ("entity_type", AuditLog.entity_type), ("actor_type", AuditLog.actor_type), ("workspace_id", AuditLog.workspace_id), ("actor_id", AuditLog.actor_id)):
        if a.get(param):
            q = q.filter(col.ilike(f"%{a[param]}%") if param == "action" else col == a[param])
    if parse_date(a.get("from")):
        q = q.filter(AuditLog.created_at >= parse_date(a["from"]))
    if parse_date(a.get("to"), end=True):
        q = q.filter(AuditLog.created_at <= parse_date(a["to"], end=True))
    if a.get("format") == "csv":
        rows = q.order_by(AuditLog.created_at.desc()).limit(50000).all()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["time", "actor_type", "actor", "action", "entity_type", "entity_id", "workspace_id", "summary", "ip"])
        for r in rows:
            w.writerow([r.created_at.isoformat(), r.actor_type, r.actor_label, r.action, r.entity_type, r.entity_id, r.workspace_id, (r.summary or "").replace("\n", " "), r.ip])
        return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": 'attachment; filename="audit-logs.csv"'})
    page, per = max(int(a.get("page", 1)), 1), min(int(a.get("per_page", 50)), MAX_PER_PAGE)
    total = q.count()
    rows = q.order_by(AuditLog.created_at.desc()).limit(per).offset((page - 1) * per).all()
    wsn = {w.id: w.name for w in db.session.query(Workspace.id, Workspace.name).filter(Workspace.id.in_({r.workspace_id for r in rows if r.workspace_id}))} if rows else {}
    return ok([{**r.to_dict(), "workspace_name": wsn.get(r.workspace_id)} for r in rows], {"page": page, "per_page": per, "total": total, "pages": max((total + per - 1) // per, 1)})


@bp.get("/system")
@admin_required()
def system():
    s, now = db.session, utcnow()
    checks = {}
    try:
        s.execute(text("select 1"))
        checks["database"] = {"ok": True}
    except Exception as e:  # pragma: no cover
        checks["database"] = {"ok": False, "error": str(e)[:100]}
    r = cache.client()
    checks["redis"] = {"ok": bool(r)}
    queue_len = None
    try:
        queue_len = r.llen("celery") if r else None
    except Exception:
        pass
    checks["job_queue"] = {"ok": r is not None, "pending": queue_len}
    checks["storage"] = {"ok": True, "backend": current_app.config["STORAGE_BACKEND"]}
    checks["billing_provider"] = {"ok": True, "provider": current_app.config["BILLING_PROVIDER"]}
    checks["email_provider"] = {"ok": True, "provider": current_app.config["EMAIL_PROVIDER"]}
    checks["ai_provider"] = {"ok": True, "provider": current_app.config["AI_PROVIDER"]}
    day = now - dt.timedelta(days=1)
    email_stats = dict(s.query(EmailLog.status, func.count()).filter(EmailLog.created_at >= day).group_by(EmailLog.status).all())
    hooks = dict(s.query(WebhookEvent.status, func.count()).filter(WebhookEvent.created_at >= now - dt.timedelta(days=7)).group_by(WebhookEvent.status).all())
    return ok({
        "checks": checks, "time": now.isoformat(),
        "jobs": {"recent": [j.to_dict() for j in s.query(JobLog).order_by(JobLog.created_at.desc()).limit(20)],
                 "failed": [j.to_dict() for j in s.query(JobLog).filter(JobLog.status == "failed").order_by(JobLog.created_at.desc()).limit(20)]},
        "email": {"last_24h": email_stats, "failures": [e.to_dict() for e in s.query(EmailLog).filter(EmailLog.status == "failed").order_by(EmailLog.created_at.desc()).limit(15)]},
        "webhooks": {"last_7d": hooks, "recent": [w.to_dict(exclude=("payload",)) for w in s.query(WebhookEvent).order_by(WebhookEvent.created_at.desc()).limit(15)],
                     "failures": [w.to_dict(exclude=("payload",)) for w in s.query(WebhookEvent).filter(WebhookEvent.status == "failed").order_by(WebhookEvent.created_at.desc()).limit(10)]},
        "api_errors": {"last_24h": s.query(func.count(ApiErrorLog.id)).filter(ApiErrorLog.created_at >= day).scalar(), "recent": [e.to_dict() for e in s.query(ApiErrorLog).order_by(ApiErrorLog.created_at.desc()).limit(15)]},
        "integration_errors": [{"workspace_id": str(i.workspace_id), "provider": i.provider, "status": i.status, "error": i.last_error, "updated_at": i.updated_at.isoformat()} for i in
                               s.query(Integration).filter(Integration.status.in_(("error", "reconnect"))).order_by(Integration.updated_at.desc()).limit(20)],
        "auth_events": [e.to_dict() for e in s.query(AuthEvent).filter(AuthEvent.event.in_(("login_failed", "lockout", "2fa_failed", "refresh_reuse_detected"))).order_by(AuthEvent.created_at.desc()).limit(15)],
    })


# ---- settings / flags / templates --------------------------------------------------------

@bp.get("/settings")
@admin_required()
def get_settings():
    from app.core.features import DEFAULT_PLATFORM_SETTINGS

    rows = {r.key: r for r in db.session.query(PlatformSetting)}
    return ok([{"key": k, "value": (rows[k].value if k in rows else v[0]), "description": v[1]} for k, v in DEFAULT_PLATFORM_SETTINGS.items()])


class SettingIn(Schema):
    value: dict


@bp.put("/settings/<key>")
@admin_required("superadmin")
def put_setting(key):
    from app.core.features import DEFAULT_PLATFORM_SETTINGS

    if key not in DEFAULT_PLATFORM_SETTINGS:
        raise not_found("Setting")
    d = parse(SettingIn)
    v = d.value
    if key in ("trial_days", "grace_days") and not (isinstance(v.get("value"), int) and 0 <= v["value"] <= 365):
        raise ApiError(422, "validation_error", "Enter a whole number of days between 0 and 365", {"value": "Invalid"})
    if key == "tax" and not (0 <= float(v.get("percent", -1)) <= 100):
        raise ApiError(422, "validation_error", "Tax percent must be between 0 and 100", {"percent": "Invalid"})
    row = db.session.get(PlatformSetting, key) or PlatformSetting(key=key, value={}, description=DEFAULT_PLATFORM_SETTINGS[key][1])
    before = dict(row.value or {})
    row.value = v
    db.session.add(row)
    audit.record("admin.setting_changed", entity_type="setting", entity_id=key, summary=f"Changed platform setting {key}", before=before, after=v)
    db.session.commit()
    return ok({"key": key, "value": v})


@bp.get("/feature-flags")
@admin_required()
def flags():
    from app.core.features import FEATURES

    wsn = {str(w.id): w.name for w in db.session.query(Workspace.id, Workspace.name)}
    return ok([{**f.to_dict(), "overrides": [{"workspace_id": k, "workspace": wsn.get(k, "Unknown"), "enabled": v} for k, v in (f.workspace_overrides or {}).items()]} for f in db.session.query(FeatureFlag).order_by(FeatureFlag.key)])


class FlagIn(Schema):
    enabled: bool | None = None
    rollout_percent: int | None = Field(default=None, ge=0, le=100)
    workspace_override: dict | None = None  # {"workspace_id": "...", "enabled": true|false|null}


@bp.patch("/feature-flags/<key>")
@admin_required("superadmin")
def update_flag(key):
    f = db.session.get(FeatureFlag, key)
    if f is None:
        raise not_found("Feature flag")
    d = parse(FlagIn)
    before = {"enabled": f.enabled, "rollout_percent": f.rollout_percent, "overrides": dict(f.workspace_overrides or {})}
    if d.enabled is not None:
        f.enabled = d.enabled
    if d.rollout_percent is not None:
        f.rollout_percent = d.rollout_percent
    if d.workspace_override:
        o = dict(f.workspace_overrides or {})
        wid, en = d.workspace_override.get("workspace_id"), d.workspace_override.get("enabled")
        if not wid or not db.session.get(Workspace, wid):
            raise ApiError(422, "validation_error", "Unknown workspace", {"workspace_override": "Unknown workspace"})
        if en is None:
            o.pop(wid, None)
        else:
            o[wid] = bool(en)
        f.workspace_overrides = o
    audit.record("admin.feature_flag_changed", entity_type="feature_flag", entity_id=key, summary=f"Updated feature flag {key}", before=before,
                 after={"enabled": f.enabled, "rollout_percent": f.rollout_percent, "overrides": dict(f.workspace_overrides or {})})
    db.session.commit()
    return ok(f.to_dict())


@bp.get("/email-templates")
@admin_required()
def templates():
    return ok([t.to_dict() for t in db.session.query(PlatformEmailTemplate).order_by(PlatformEmailTemplate.name)])


class TemplateIn(Schema):
    subject: str = Field(min_length=1, max_length=300)
    body_html: str = Field(min_length=1, max_length=50000)


@bp.put("/email-templates/<key>")
@admin_required("superadmin")
def update_template(key):
    t = db.session.get(PlatformEmailTemplate, key)
    if t is None:
        raise not_found("Template")
    d = parse(TemplateIn)
    if "<script" in d.body_html.lower():
        raise ApiError(422, "validation_error", "Scripts aren't allowed in email templates", {"body_html": "Not allowed"})
    try:  # fail fast on broken Jinja syntax
        email_service.check_syntax(d.body_html, d.subject)
    except Exception as e:
        raise ApiError(422, "validation_error", f"Template syntax error: {e}", {"body_html": "Syntax error"})
    before = {"subject": t.subject}
    t.subject, t.body_html = d.subject, d.body_html
    audit.record("admin.email_template_changed", entity_type="email_template", entity_id=key, summary=f"Edited email template “{t.name}”", before=before, after={"subject": t.subject})
    db.session.commit()
    return ok(t.to_dict())


def _sample_ctx(t: PlatformEmailTemplate) -> dict:
    return {v: f"[{v}]" for v in t.variables} | {"app_url": current_app.config["WEB_ORIGIN"], "billing_url": current_app.config["WEB_ORIGIN"] + "/app/billing"}


@bp.get("/email-templates/<key>/preview")
@admin_required()
def preview_template(key):
    t = db.session.get(PlatformEmailTemplate, key)
    if t is None:
        raise not_found("Template")
    subject, html = email_service.render_template(key, _sample_ctx(t))
    return ok({"subject": subject, "html": html})


@bp.post("/email-templates/<key>/send-test")
@admin_required("superadmin")
def send_test_template(key):
    t = db.session.get(PlatformEmailTemplate, key)
    if t is None:
        raise not_found("Template")
    ok_ = email_service.send_template(key, g.admin.email, _sample_ctx(t))
    db.session.commit()
    return ok({"sent": ok_, "to": g.admin.email})


# ---- admin users -------------------------------------------------------------------------

@bp.get("/admins")
@admin_required("superadmin")
def admins():
    return ok([admin_dict(a) | {"status": a.status} for a in db.session.query(AdminUser).order_by(AdminUser.created_at)])


class AdminIn(Schema):
    email: Email
    name: str = Field(min_length=1, max_length=160)
    password: str
    role: str = Field(default="support", pattern="^(superadmin|support|finance)$")


@bp.post("/admins")
@admin_required("superadmin", recent_mfa=True)
def create_admin():
    d = parse(AdminIn)
    if password_problems(d.password) or len(d.password) < 12:
        raise ApiError(422, "validation_error", "Admin passwords need 12+ characters with letters and numbers", {"password": "Too weak"})
    if db.session.query(AdminUser).filter_by(email=d.email).first():
        raise conflict("An admin with that email already exists")
    a = AdminUser(email=d.email, name=d.name, password_hash=hash_password(d.password), role=d.role)
    db.session.add(a)
    db.session.flush()
    audit.record("admin.admin_created", entity_type="admin", entity_id=a.id, summary=f"Created {d.role} admin {d.email}")
    db.session.commit()
    return created(admin_dict(a))
