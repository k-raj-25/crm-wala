"""Billing domain logic: pricing, coupons, proration, subscription state, invoices, lifecycle jobs.

All provider webhooks and the mock checkout converge on `apply_event`, so behaviour is identical in dev and prod.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from sqlalchemy import func

from app.core.errors import ApiError, bad_request, conflict, not_found
from app.extensions import db
from app.models import (
    CheckoutSession, Coupon, CouponRedemption, Invoice, Payment, Plan, Subscription, User, Workspace,
)
from app.models.base import utcnow
from app.services import analytics, audit, notifications
from app.services import email as email_service
from app.services import settings as platform_settings
from app.services.billing.providers import get_provider
from app.services.billing.types import BillingEvent
from app.services.features import get_plan

log = logging.getLogger("app.billing")
PERIOD = {"monthly": 30, "annual": 365}


def price_for(plan: Plan, interval: str) -> int:
    if plan.is_trial or plan.is_custom or plan.price_monthly is None:
        raise ApiError(422, "validation_error", "This plan can't be purchased online. Contact sales.", {"plan_key": "Not purchasable"})
    if interval == "annual":
        return plan.price_annual if plan.price_annual is not None else plan.price_monthly * 10
    return plan.price_monthly


def tax_rate() -> tuple[str, float]:
    return platform_settings.get_setting("tax", "name", "Tax"), float(platform_settings.get_setting("tax", "percent", 0))


def find_coupon(code: str, plan_key: str, workspace_id) -> Coupon:
    c = db.session.query(Coupon).filter(func.upper(Coupon.code) == code.strip().upper()).one_or_none()
    if c is None or not c.is_active:
        raise ApiError(422, "invalid_coupon", "That coupon code isn't valid.", {"coupon_code": "Invalid code"})
    if c.valid_until and c.valid_until < utcnow():
        raise ApiError(422, "invalid_coupon", "That coupon has expired.", {"coupon_code": "Expired"})
    if c.max_redemptions is not None and c.times_redeemed >= c.max_redemptions:
        raise ApiError(422, "invalid_coupon", "That coupon has been fully redeemed.", {"coupon_code": "Fully redeemed"})
    if c.plan_keys and plan_key not in c.plan_keys:
        raise ApiError(422, "invalid_coupon", "That coupon doesn't apply to this plan.", {"coupon_code": "Not valid for this plan"})
    if db.session.query(CouponRedemption).filter_by(coupon_id=c.id, workspace_id=workspace_id).first():
        raise ApiError(422, "invalid_coupon", "You've already used this coupon.", {"coupon_code": "Already used"})
    return c


def quote(ws: Workspace, plan_key: str, interval: str, coupon_code: str | None = None) -> dict:
    if interval not in PERIOD:
        raise bad_request("interval must be monthly or annual")
    plan = get_plan(plan_key)
    if plan is None or not plan.is_active:
        raise not_found("Plan")
    subtotal = price_for(plan, interval)
    discount, coupon = 0, None
    if coupon_code:
        coupon = find_coupon(coupon_code, plan_key, ws.id)
        discount = int(subtotal * coupon.percent_off / 100) if coupon.percent_off else min(coupon.amount_off or 0, subtotal)
    credit = 0
    sub = active_subscription(ws)
    if sub and sub.current_period_end and sub.amount and sub.plan_key != plan_key and ws.subscription_status == "active":
        total_days = PERIOD.get(sub.interval, 30)
        remaining = max((sub.current_period_end - utcnow()).total_seconds() / 86400, 0)
        credit = int(sub.amount * min(remaining / total_days, 1))
    after_discount = max(subtotal - discount, 0)
    wallet = min(ws.credit_balance or 0, max(after_discount - credit, 0))
    taxable = max(after_discount - credit - wallet, 0)
    tax_name, pct = tax_rate()
    tax = int(round(taxable * pct / 100))
    return {"plan_key": plan_key, "plan_name": plan.name, "interval": interval, "currency": plan.currency, "subtotal": subtotal, "discount": discount,
            "coupon": coupon.code if coupon else None, "proration_credit": credit, "account_credit": wallet, "tax_name": tax_name, "tax_percent": pct, "tax": tax,
            "total": taxable + tax}


def active_subscription(ws: Workspace) -> Subscription | None:
    return db.session.query(Subscription).filter(Subscription.workspace_id == ws.id, Subscription.status.in_(("active", "past_due"))).order_by(Subscription.created_at.desc()).first()


def start_checkout(ws: Workspace, user: User, plan_key: str, interval: str, coupon_code: str | None) -> dict:
    q = quote(ws, plan_key, interval, coupon_code)
    plan = get_plan(plan_key)
    provider = get_provider()
    cs = CheckoutSession(workspace_id=ws.id, plan_key=plan_key, interval=interval, coupon_code=q["coupon"], amount=q["subtotal"] - q["discount"], currency=q["currency"],
                         provider=provider.name, created_by=user.id)
    db.session.add(cs)
    db.session.flush()
    res = provider.create_checkout(ws, cs, plan.name, user.email)
    cs.provider_session_id = res.provider_session_id
    audit.record("billing.checkout_started", entity_type="workspace", entity_id=ws.id, summary=f"Started checkout for {plan.name} ({interval})", after=q)
    return {"url": res.url, "session_id": res.provider_session_id, "quote": q}


def _next_invoice_number() -> str:
    n = (db.session.query(func.count(Invoice.id)).scalar() or 0) + 1
    return f"INV-{utcnow():%Y}-{n:06d}"


def apply_event(ev: BillingEvent, provider_name: str) -> str:
    """Idempotent state transition. Returns a short outcome string for logs."""
    cs = None
    if ev.checkout_session_id:
        try:
            cs = db.session.get(CheckoutSession, uuid.UUID(ev.checkout_session_id))
        except ValueError:
            cs = None
    ws = db.session.get(Workspace, uuid.UUID(ev.workspace_id)) if ev.workspace_id else (db.session.get(Workspace, cs.workspace_id) if cs else None)
    sub = db.session.query(Subscription).filter_by(provider_subscription_id=ev.provider_subscription_id).first() if ev.provider_subscription_id else None
    if ws is None and sub is not None:
        ws = db.session.get(Workspace, sub.workspace_id)
    if ws is None:
        return "ignored: unknown workspace"
    if ev.type == "checkout_completed":
        if ev.raw.get("customer"):
            ws.provider_customer_id = ev.raw["customer"]
        return "customer linked"
    if ev.type == "payment_succeeded":
        return _on_payment_succeeded(ws, sub, cs, ev, provider_name)
    if ev.type == "payment_failed":
        return _on_payment_failed(ws, sub, ev, provider_name)
    if ev.type == "subscription_canceled":
        if sub:
            sub.status, sub.ended_at = "ended", utcnow()
        ws.subscription_status = "canceled" if ws.current_period_end and ws.current_period_end > utcnow() else "expired"
        ws.cancel_at_period_end = False
        return "subscription ended"
    return "ignored"


def _on_payment_succeeded(ws, sub, cs, ev, provider_name) -> str:
    if ev.provider_payment_id and db.session.query(Payment).filter_by(provider=provider_name, provider_payment_id=ev.provider_payment_id).first():
        return "duplicate payment ignored"
    plan_key = cs.plan_key if cs else (sub.plan_key if sub else ws.plan_key)
    interval = cs.interval if cs else (sub.interval if sub else "monthly")
    plan = get_plan(plan_key)
    now = utcnow()
    start = ev.period_start or now
    end = ev.period_end or (start + dt.timedelta(days=PERIOD[interval]))
    coupon_code = cs.coupon_code if cs else (sub.coupon_code if sub else None)
    q = quote(ws, plan_key, interval, None) if plan and not plan.is_custom else None
    subtotal = q["subtotal"] if q else ev.amount
    discount = 0
    if coupon_code:
        coupon = db.session.query(Coupon).filter(func.upper(Coupon.code) == coupon_code.upper()).first()
        if coupon:
            discount = int(subtotal * coupon.percent_off / 100) if coupon.percent_off else min(coupon.amount_off or 0, subtotal)
            if not db.session.query(CouponRedemption).filter_by(coupon_id=coupon.id, workspace_id=ws.id).first():
                db.session.add(CouponRedemption(coupon_id=coupon.id, workspace_id=ws.id))
                coupon.times_redeemed += 1
    if sub is None:
        # New subscription replaces any existing one (upgrade/switch): end the old, keep one ledger row active.
        old = active_subscription(ws)
        if old:
            old.status, old.ended_at = "ended", now
        sub = Subscription(workspace_id=ws.id, plan_key=plan_key, interval=interval, status="active", amount=ev.amount or subtotal - discount, currency=ev.currency,
                           coupon_code=coupon_code, provider=provider_name, provider_subscription_id=ev.provider_subscription_id)
        db.session.add(sub)
        analytics.track("subscription_started", {"plan": plan_key, "interval": interval, "amount": ev.amount}, workspace_id=ws.id)
    was_pastdue = ws.subscription_status == "past_due"
    sub.status, sub.current_period_start, sub.current_period_end = "active", start, end
    sub.plan_key, sub.interval = plan_key, interval
    if ev.payment_method:
        sub.payment_method = {k: v for k, v in ev.payment_method.items() if k in ("brand", "last4", "exp")}
    if cs:
        cs.status = "completed"
    ws.plan_key, ws.billing_interval, ws.subscription_status = plan_key, interval, "active"
    ws.current_period_end, ws.grace_ends_at, ws.cancel_at_period_end = end, None, False
    db.session.flush()
    payment = Payment(workspace_id=ws.id, subscription_id=sub.id, amount=ev.amount, currency=ev.currency, status="succeeded", provider=provider_name,
                      provider_payment_id=ev.provider_payment_id, description=f"{plan.name if plan else plan_key} ({interval})")
    db.session.add(payment)
    db.session.flush()
    tax_name, pct = tax_rate()
    # Provider charged `ev.amount` (tax-inclusive of what we told it); reconstruct the invoice lines.
    taxable = max(subtotal - discount, 0)
    tax = int(round(taxable * pct / 100)) if q else 0
    inv = Invoice(workspace_id=ws.id, payment_id=payment.id, number=_next_invoice_number(), subtotal=subtotal, discount=discount, tax=tax, total=ev.amount or taxable + tax,
                  currency=ev.currency, period_start=start, period_end=end,
                  line_items=[{"description": f"CRM Wala {plan.name if plan else plan_key} — {interval}", "amount": subtotal, "quantity": 1}],
                  billing_details={"name": ws.name, "tax_name": tax_name, "tax_percent": pct})
    db.session.add(inv)
    owner = db.session.get(User, ws.owner_id)
    audit.record("billing.payment_succeeded", entity_type="payment", entity_id=payment.id, workspace_id=ws.id, actor_type="system",
                 summary=f"Payment of {ev.amount / 100:,.2f} {ev.currency} received for {plan_key}")
    if owner:
        email_service.send_template("payment_successful", owner.email, {"name": owner.name, "amount": f"{ev.currency} {ev.amount / 100:,.2f}", "plan": plan.name if plan else plan_key,
                                                                      "invoice_number": inv.number}, workspace_id=ws.id)
    notifications.notify(ws.id, notifications.workspace_admins(ws.id), "system", "Payment received",
                         f"Thanks! Your {plan.name if plan else plan_key} plan is active until {end:%d %b %Y}.", "/app/billing")
    if was_pastdue:
        notifications.notify(ws.id, notifications.workspace_admins(ws.id), "payment_issue", "Payment recovered", "Your account is back in good standing.", "/app/billing")
    return "payment recorded"


def _on_payment_failed(ws, sub, ev, provider_name) -> str:
    if ev.provider_payment_id and db.session.query(Payment).filter_by(provider=provider_name, provider_payment_id=ev.provider_payment_id).first():
        return "duplicate ignored"
    grace = dt.timedelta(days=platform_settings.grace_days())
    db.session.add(Payment(workspace_id=ws.id, subscription_id=sub.id if sub else None, amount=ev.amount, currency=ev.currency, status="failed", provider=provider_name,
                           provider_payment_id=ev.provider_payment_id, failure_reason=ev.failure_reason or "Payment failed", description="Subscription payment"))
    if ws.subscription_status == "active":
        ws.subscription_status, ws.grace_ends_at = "past_due", utcnow() + grace
        if sub:
            sub.status = "past_due"
        owner = db.session.get(User, ws.owner_id)
        if owner:
            email_service.send_template("payment_failed", owner.email, {"name": owner.name, "workspace": ws.name,
                                                                      "grace_ends": ws.grace_ends_at.strftime("%d %b %Y")}, workspace_id=ws.id)
        notifications.notify(ws.id, notifications.workspace_admins(ws.id), "payment_issue", "Payment failed",
                             f"We couldn't charge your card. You keep full access until {ws.grace_ends_at:%d %b}.", "/app/billing")
        from app.services.automation import dispatch

        dispatch(ws.id, "payment.failed", {"workspace_id": str(ws.id)})
    audit.record("billing.payment_failed", entity_type="workspace", entity_id=ws.id, workspace_id=ws.id, actor_type="system", summary=f"Payment failed: {ev.failure_reason or 'declined'}")
    return "failure recorded"


def cancel(ws: Workspace, immediately: bool = False) -> Subscription:
    sub = active_subscription(ws)
    if sub is None:
        raise conflict("There's no active subscription to cancel", "no_subscription")
    get_provider(sub.provider).cancel(sub, at_period_end=not immediately)
    sub.canceled_at = utcnow()
    if immediately:
        sub.status, sub.ended_at = "ended", utcnow()
        ws.subscription_status = "expired"
    else:
        sub.cancel_at_period_end = True
        ws.cancel_at_period_end = True
    owner = db.session.get(User, ws.owner_id)
    if owner:
        email_service.send_template("subscription_cancelled", owner.email, {"name": owner.name, "workspace": ws.name,
                                                                          "access_until": (ws.current_period_end or utcnow()).strftime("%d %b %Y")}, workspace_id=ws.id)
    analytics.track("subscription_cancelled", {"plan": sub.plan_key, "immediately": immediately}, workspace_id=ws.id)
    audit.record("billing.subscription_canceled", entity_type="workspace", entity_id=ws.id, workspace_id=ws.id, summary=f"Subscription canceled ({'now' if immediately else 'at period end'})")
    return sub


def resume(ws: Workspace) -> Subscription:
    sub = active_subscription(ws)
    if sub is None or not sub.cancel_at_period_end:
        raise conflict("Nothing to resume", "nothing_to_resume")
    get_provider(sub.provider).resume(sub)
    sub.cancel_at_period_end, sub.canceled_at = False, None
    ws.cancel_at_period_end = False
    if ws.subscription_status == "canceled":
        ws.subscription_status = "active"
    audit.record("billing.subscription_resumed", entity_type="workspace", entity_id=ws.id, workspace_id=ws.id, summary="Subscription resumed")
    return sub


def schedule_downgrade(ws: Workspace, plan_key: str, interval: str) -> Subscription:
    sub = active_subscription(ws)
    plan = get_plan(plan_key)
    if sub is None or plan is None:
        raise conflict("There's no active subscription", "no_subscription")
    price_for(plan, interval)
    sub.pending_plan_key, sub.pending_interval = plan_key, interval
    audit.record("billing.downgrade_scheduled", entity_type="workspace", entity_id=ws.id, workspace_id=ws.id, summary=f"Downgrade to {plan_key} scheduled for period end")
    return sub


def is_downgrade(ws: Workspace, plan_key: str, interval: str) -> bool:
    cur = get_plan(ws.plan_key)
    new = get_plan(plan_key)
    if cur is None or new is None or cur.price_monthly is None or new.price_monthly is None or ws.subscription_status != "active":
        return False
    return new.price_monthly < cur.price_monthly


# ---- Lifecycle (called from Celery beat; also safe to call ad hoc) ----------------------

def run_lifecycle(now: dt.datetime | None = None) -> dict:
    """Trial reminders + expiry, grace expiry, scheduled downgrades, cancellations reaching period end, mock renewals."""
    from app.core.tenant import bypass_scope

    now = now or utcnow()
    stats = {"trial_reminders": 0, "trials_expired": 0, "grace_expired": 0, "downgrades": 0, "canceled_ended": 0, "renewed": 0}
    with bypass_scope():
        for ws in db.session.query(Workspace).filter(Workspace.deleted_at.is_(None), Workspace.subscription_status == "trialing", Workspace.trial_ends_at.isnot(None)).all():
            owner = db.session.get(User, ws.owner_id)
            sent = set(ws.trial_milestones_sent or [])
            remaining = ws.trial_ends_at - now
            if remaining <= dt.timedelta(0):
                ws.subscription_status = "expired"
                if "expired" not in sent and owner:
                    email_service.send_template("trial_expired", owner.email, {"name": owner.name, "workspace": ws.name}, workspace_id=ws.id)
                    notifications.notify(ws.id, notifications.workspace_admins(ws.id), "trial_ending", "Your trial has ended", "Choose a plan to continue.", "/app/billing")
                    sent.add("expired")
                analytics.track("trial_expired", workspace_id=ws.id)
                stats["trials_expired"] += 1
            elif remaining <= dt.timedelta(hours=24) and "final" not in sent:
                if owner:
                    email_service.send_template("trial_ending", owner.email, {"name": owner.name, "workspace": ws.name, "when": "today"}, workspace_id=ws.id)
                notifications.notify(ws.id, notifications.workspace_admins(ws.id), "trial_ending", "Your trial ends today", "Choose a plan to keep access to your CRM.", "/app/billing")
                from app.services.automation import dispatch

                dispatch(ws.id, "trial.ending", {"workspace_id": str(ws.id)})
                sent.add("final")
                stats["trial_reminders"] += 1
            elif remaining <= dt.timedelta(hours=48) and "day2" not in sent:
                if owner:
                    email_service.send_template("trial_ending", owner.email, {"name": owner.name, "workspace": ws.name, "when": "tomorrow"}, workspace_id=ws.id)
                notifications.notify(ws.id, notifications.workspace_admins(ws.id), "trial_ending", "Your trial ends tomorrow", "Choose a plan to keep access.", "/app/billing")
                sent.add("day2")
                stats["trial_reminders"] += 1
            ws.trial_milestones_sent = sorted(sent)
        for ws in db.session.query(Workspace).filter(Workspace.subscription_status == "past_due", Workspace.grace_ends_at < now).all():
            stats["grace_expired"] += 1  # access is restricted by compute_access(); nothing to mutate, but record once
            audit.record("billing.grace_expired", entity_type="workspace", entity_id=ws.id, workspace_id=ws.id, actor_type="system", summary="Grace period ended; workspace restricted")
            ws.grace_ends_at = ws.grace_ends_at  # keep value for display
        for ws in db.session.query(Workspace).filter(Workspace.subscription_status == "canceled", Workspace.current_period_end < now).all():
            ws.subscription_status = "expired"
            stats["canceled_ended"] += 1
        for sub in db.session.query(Subscription).filter(Subscription.status.in_(("active",)), Subscription.current_period_end < now, Subscription.provider == "mock").all():
            ws = db.session.get(Workspace, sub.workspace_id)
            if ws is None:
                continue
            if sub.cancel_at_period_end:
                sub.status, sub.ended_at = "ended", now
                ws.subscription_status = "expired"
                stats["canceled_ended"] += 1
                continue
            plan_key, interval = sub.pending_plan_key or sub.plan_key, sub.pending_interval or sub.interval
            plan = get_plan(plan_key)
            amount = price_for(plan, interval)
            fail = (ws.settings or {}).get("mock_fail_next_payment")
            ev_id = f"mock_renew_{sub.id}_{int(now.timestamp())}"
            if fail:
                ws.settings = {k: v for k, v in (ws.settings or {}).items() if k != "mock_fail_next_payment"}
                apply_event(BillingEvent(id=ev_id, type="payment_failed", workspace_id=str(ws.id), provider_subscription_id=sub.provider_subscription_id, provider_payment_id=ev_id,
                                         amount=amount, currency=plan.currency, failure_reason="Card declined (simulated)"), "mock")
            else:
                q = quote(ws, plan_key, interval)
                sub.pending_plan_key = sub.pending_interval = None
                apply_event(BillingEvent(id=ev_id, type="payment_succeeded", workspace_id=str(ws.id), provider_subscription_id=sub.provider_subscription_id, provider_payment_id=ev_id,
                                         amount=q["total"], currency=plan.currency, period_start=sub.current_period_end,
                                         period_end=sub.current_period_end + dt.timedelta(days=PERIOD[interval])), "mock")
                stats["renewed"] += 1
        db.session.commit()
    return stats
