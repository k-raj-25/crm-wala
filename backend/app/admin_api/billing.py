"""Super Admin billing: plans, pricing, limits, features, coupons, payments, refunds. No deploy needed to change any of it."""
from __future__ import annotations

import datetime as dt

from flask import Blueprint, current_app, g, request
from pydantic import Field, field_validator
from sqlalchemy import func, or_

from app.admin_api.auth import admin_required
from app.core.crud import MAX_PER_PAGE
from app.core.errors import ApiError, conflict, not_found
from app.core.features import ALL_FEATURES
from app.core.responses import created, ok
from app.extensions import db
from app.models import Coupon, CouponRedemption, Invoice, Payment, Plan, Subscription, Workspace
from app.models.base import utcnow
from app.schemas.common import Schema, parse, provided
from app.services import audit
from app.services.usage import LABELS

bp = Blueprint("admin_billing", __name__, url_prefix="/admin-api/v1")


def _plan_dict(p: Plan) -> dict:
    counts = dict(db.session.query(Workspace.plan_key, func.count()).filter(Workspace.deleted_at.is_(None)).group_by(Workspace.plan_key).all())
    return {**p.to_dict(), "workspaces": counts.get(p.key, 0)}


@bp.get("/plans")
@admin_required()
def plans():
    counts = dict(db.session.query(Workspace.plan_key, func.count()).filter(Workspace.deleted_at.is_(None)).group_by(Workspace.plan_key).all())
    return ok({"plans": [{**p.to_dict(), "workspaces": counts.get(p.key, 0)} for p in db.session.query(Plan).order_by(Plan.sort_order)], "limit_keys": LABELS, "features": ALL_FEATURES})


class PlanIn(Schema):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,38}$")
    name: str = Field(min_length=1, max_length=80)
    tagline: str | None = Field(default=None, max_length=200)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    price_monthly: int | None = Field(default=None, ge=0, le=1_000_000_00)
    price_annual: int | None = Field(default=None, ge=0, le=10_000_000_00)
    limits: dict[str, int | None] = Field(default_factory=dict)
    features: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list, max_length=12)
    is_public: bool = True
    is_active: bool = True
    is_custom: bool = False
    sort_order: int = 0

    @field_validator("limits")
    @classmethod
    def _limits(cls, v):
        bad = [k for k in v if k not in LABELS]
        if bad:
            raise ValueError(f"Unknown limit keys: {', '.join(bad)}")
        return v

    @field_validator("features")
    @classmethod
    def _features(cls, v):
        bad = [k for k in v if k not in ALL_FEATURES]
        if bad:
            raise ValueError(f"Unknown features: {', '.join(bad)}")
        return v


@bp.post("/plans")
@admin_required("superadmin", "finance")
def create_plan():
    d = parse(PlanIn)
    if db.session.query(Plan).filter_by(key=d.key).first():
        raise conflict("A plan with that key already exists")
    p = Plan(**d.model_dump())
    db.session.add(p)
    db.session.flush()
    audit.record("admin.plan_created", entity_type="plan", entity_id=p.key, summary=f"Created plan {p.name}", after=p.to_dict())
    db.session.commit()
    return created(_plan_dict(p))


@bp.patch("/plans/<key>")
@admin_required("superadmin", "finance")
def update_plan(key):
    p = db.session.query(Plan).filter_by(key=key).one_or_none()
    if p is None:
        raise not_found("Plan")
    body = request.get_json(silent=True) or {}
    merged = {**{f: getattr(p, f) for f in PlanIn.model_fields}, **{k: v for k, v in body.items() if k in PlanIn.model_fields and k != "key"}}
    d = parse(PlanIn, merged)
    if p.is_trial and not d.is_active:
        raise ApiError(409, "plan_protected", "The trial plan can't be disabled. Set the trial length in Settings.")
    if not d.is_active and db.session.query(Workspace).filter(Workspace.plan_key == key, Workspace.subscription_status == "active", Workspace.deleted_at.is_(None)).count():
        # allowed: existing subscribers keep the plan; it just stops being offered
        pass
    before = p.to_dict()
    for k, v in d.model_dump().items():
        if k != "key":
            setattr(p, k, v)
    from app.services.audit import diff

    b, a = diff(before, p.to_dict())
    audit.record("admin.plan_updated", entity_type="plan", entity_id=p.key, summary=f"Updated plan {p.name}", before=b, after=a)
    db.session.commit()
    return ok(_plan_dict(p))


# ---- coupons -----------------------------------------------------------------------------

class CouponIn(Schema):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{3,40}$")
    description: str | None = Field(default=None, max_length=200)
    percent_off: int | None = Field(default=None, ge=1, le=100)
    amount_off: int | None = Field(default=None, ge=1)
    currency: str = "INR"
    duration: str = Field(default="once", pattern="^(once|forever|repeating)$")
    duration_months: int | None = Field(default=None, ge=1, le=36)
    max_redemptions: int | None = Field(default=None, ge=1)
    valid_until: dt.datetime | None = None
    plan_keys: list[str] = Field(default_factory=list)
    is_active: bool = True


@bp.get("/coupons")
@admin_required()
def coupons():
    return ok([c.to_dict() for c in db.session.query(Coupon).order_by(Coupon.created_at.desc())])


@bp.post("/coupons")
@admin_required("superadmin", "finance")
def create_coupon():
    d = parse(CouponIn)
    if bool(d.percent_off) == bool(d.amount_off):
        raise ApiError(422, "validation_error", "Set either a percentage or a fixed amount", {"percent_off": "Choose one discount type"})
    code = d.code.upper()
    if db.session.query(Coupon).filter(func.upper(Coupon.code) == code).first():
        raise conflict("That coupon code already exists")
    c = Coupon(**{**d.model_dump(), "code": code})
    db.session.add(c)
    db.session.flush()
    audit.record("admin.coupon_created", entity_type="coupon", entity_id=c.id, summary=f"Created coupon {code}", after=c.to_dict())
    db.session.commit()
    return created(c.to_dict())


@bp.patch("/coupons/<uuid:cid>")
@admin_required("superadmin", "finance")
def update_coupon(cid):
    c = db.session.get(Coupon, cid)
    if c is None:
        raise not_found("Coupon")

    class In(Schema):
        is_active: bool | None = None
        max_redemptions: int | None = None
        valid_until: dt.datetime | None = None
        description: str | None = None

    ch = provided(parse(In))
    for k, v in ch.items():
        setattr(c, k, v)
    audit.record("admin.coupon_updated", entity_type="coupon", entity_id=c.id, summary=f"Updated coupon {c.code}", after={k: str(v) for k, v in ch.items()})
    db.session.commit()
    return ok(c.to_dict())


# ---- revenue & payments ------------------------------------------------------------------

@bp.get("/billing/overview")
@admin_required()
def overview():
    from app.admin_api.platform import mrr_cents

    s, now = db.session, utcnow()
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    gross = s.query(func.coalesce(func.sum(Payment.amount), 0)).filter(Payment.status.in_(("succeeded", "refunded"))).scalar()
    refunds = s.query(func.coalesce(func.sum(Payment.refunded_amount), 0)).scalar()
    this_month = s.query(func.coalesce(func.sum(Payment.amount - Payment.refunded_amount), 0)).filter(Payment.status.in_(("succeeded", "refunded")), Payment.created_at >= month).scalar()
    mrr = mrr_cents()
    plan_rows = []
    for p in s.query(Plan).order_by(Plan.sort_order):
        subs = s.query(Subscription).filter(Subscription.plan_key == p.key, Subscription.status.in_(("active", "past_due"))).all()
        plan_rows.append({"key": p.key, "name": p.name, "active_subscriptions": len(subs), "mrr": sum(x.amount // 12 if x.interval == "annual" else x.amount for x in subs) / 100})
    return ok({
        "revenue_total": float(gross) / 100, "revenue_this_month": float(this_month) / 100, "mrr": mrr / 100, "arr": mrr * 12 / 100,
        "active_subscriptions": s.query(func.count(Subscription.id)).filter(Subscription.status.in_(("active", "past_due"))).scalar(),
        "cancelled_subscriptions": s.query(func.count(Subscription.id)).filter(or_(Subscription.status == "ended", Subscription.cancel_at_period_end.is_(True))).scalar(),
        "failed_payments": s.query(func.count(Payment.id)).filter(Payment.status == "failed", Payment.created_at >= now - dt.timedelta(days=30)).scalar(),
        "past_due_workspaces": s.query(func.count(Workspace.id)).filter(Workspace.subscription_status == "past_due", Workspace.deleted_at.is_(None)).scalar(),
        "refunds_total": float(refunds) / 100,
        "coupons": {"active": s.query(func.count(Coupon.id)).filter(Coupon.is_active.is_(True)).scalar(), "redemptions": s.query(func.count(CouponRedemption.id)).scalar()},
        "plans": plan_rows,
    })


@bp.get("/payments")
@admin_required()
def payments():
    a = request.args
    q = db.session.query(Payment, Workspace.name).join(Workspace, Workspace.id == Payment.workspace_id)
    if a.get("status"):
        q = q.filter(Payment.status == a["status"])
    if a.get("workspace_id"):
        q = q.filter(Payment.workspace_id == a["workspace_id"])
    page, per = max(int(a.get("page", 1)), 1), min(int(a.get("per_page", 25)), MAX_PER_PAGE)
    total = q.count()
    rows = q.order_by(Payment.created_at.desc()).limit(per).offset((page - 1) * per).all()
    return ok([{**p.to_dict(), "workspace": n} for p, n in rows], {"page": page, "per_page": per, "total": total, "pages": max((total + per - 1) // per, 1)})


class RefundIn(Schema):
    amount: int | None = Field(default=None, ge=1)
    reason: str = Field(min_length=1, max_length=300)


@bp.post("/payments/<uuid:pid>/refund")
@admin_required("superadmin", "finance", recent_mfa=True)
def refund(pid):
    d = parse(RefundIn)
    p = db.session.get(Payment, pid)
    if p is None or p.status not in ("succeeded", "refunded"):
        raise not_found("Refundable payment")
    amount = d.amount or (p.amount - p.refunded_amount)
    if amount <= 0 or p.refunded_amount + amount > p.amount:
        raise ApiError(422, "validation_error", "Refund amount exceeds the payment", {"amount": "Too high"})
    if p.provider == "stripe":
        import stripe

        stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
        stripe.Refund.create(payment_intent=p.provider_payment_id, amount=amount)
    elif p.provider == "razorpay":
        import httpx

        r = httpx.post(f"https://api.razorpay.com/v1/payments/{p.provider_payment_id}/refund", json={"amount": amount}, auth=(current_app.config["RAZORPAY_KEY_ID"], current_app.config["RAZORPAY_KEY_SECRET"]), timeout=20)
        if r.status_code >= 400:
            raise ApiError(502, "provider_error", "The payment provider rejected the refund.", {"provider": r.text[:200]})
    p.refunded_amount += amount
    p.status = "refunded" if p.refunded_amount >= p.amount else p.status
    if p.refunded_amount >= p.amount:
        db.session.query(Invoice).filter_by(payment_id=p.id).update({"status": "void"})
    audit.record("admin.payment_refunded", entity_type="payment", entity_id=p.id, workspace_id=p.workspace_id, summary=f"Refunded {amount / 100:,.2f} {p.currency}. {d.reason}")
    db.session.commit()
    return ok(p.to_dict())
