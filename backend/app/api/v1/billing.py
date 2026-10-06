from __future__ import annotations

import io
import json

from flask import Blueprint, Response, current_app, g, request
from pydantic import Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.auth import protect
from app.core.errors import ApiError, bad_request, conflict, not_found
from app.core.responses import ok
from app.core.tenant import bypass_scope
from app.extensions import db, limiter
from app.models import Invoice, Payment, Plan, Subscription, WebhookEvent, Workspace
from app.models.base import utcnow
from app.schemas.common import Schema, parse
from app.services import analytics, audit
from app.services import settings as platform_settings
from app.services.accounts import subscription_summary
from app.services.billing import core
from app.services.billing.providers import get_provider
from app.services.features import plan_limits
from app.services.usage import LABELS, current_usage

bp = Blueprint("billing", __name__, url_prefix="/api/v1")
public_bp = Blueprint("billing_public", __name__, url_prefix="/api/v1/public")


def plan_dict(p: Plan) -> dict:
    return {"key": p.key, "name": p.name, "tagline": p.tagline, "currency": p.currency, "price_monthly": p.price_monthly, "price_annual": p.price_annual,
            "limits": p.limits, "features": p.features, "highlights": p.highlights, "is_custom": p.is_custom, "is_trial": p.is_trial}


@public_bp.get("/plans")
def public_plans():
    rows = db.session.query(Plan).filter(Plan.is_active.is_(True), Plan.is_public.is_(True)).order_by(Plan.sort_order).all()
    name, pct = core.tax_rate()
    return ok({"plans": [plan_dict(p) for p in rows], "trial_days": platform_settings.trial_days(), "tax": {"name": name, "percent": pct}})


@bp.get("/billing/plans")
@protect("billing.manage", allow_restricted=True)
def plans():
    rows = db.session.query(Plan).filter(Plan.is_active.is_(True), db.or_(Plan.is_public.is_(True), Plan.key == g.workspace.plan_key)).order_by(Plan.sort_order).all()
    return ok([plan_dict(p) for p in rows if not p.is_trial])


@bp.get("/billing/overview")
@protect("billing.manage", allow_restricted=True)
def overview():
    ws = g.workspace
    sub = core.active_subscription(ws)
    limits = plan_limits(ws)
    usage = current_usage(ws)
    plan = db.session.query(Plan).filter_by(key=ws.plan_key).one_or_none()
    return ok({
        "subscription": subscription_summary(ws),
        "plan": plan_dict(plan) if plan else None,
        "next_billing_date": sub.current_period_end.isoformat() if sub and sub.current_period_end and not sub.cancel_at_period_end else None,
        "amount": sub.amount if sub else None, "currency": sub.currency if sub else "INR",
        "pending_plan_key": sub.pending_plan_key if sub else None,
        "payment_method": sub.payment_method if sub else None, "provider": get_provider().name,
        "credit_balance": ws.credit_balance,
        "usage": [{"key": k, "label": LABELS[k], "used": usage.get(k, 0), "limit": limits.get(k)} for k in LABELS],
    })


class QuoteIn(Schema):
    plan_key: str
    interval: str = Field(default="monthly", pattern="^(monthly|annual)$")
    coupon_code: str | None = Field(default=None, max_length=40)


@bp.post("/billing/quote")
@protect("billing.manage", allow_restricted=True)
def quote():
    d = parse(QuoteIn)
    return ok(core.quote(g.workspace, d.plan_key, d.interval, d.coupon_code))


@bp.post("/billing/checkout")
@protect("billing.manage", allow_restricted=True)
@limiter.limit("20 per hour")
def checkout():
    d = parse(QuoteIn)
    ws = g.workspace
    if ws.subscription_status == "active" and ws.plan_key == d.plan_key and ws.billing_interval == d.interval:
        raise conflict("You're already on this plan", "same_plan")
    if core.is_downgrade(ws, d.plan_key, d.interval):
        sub = core.schedule_downgrade(ws, d.plan_key, d.interval)
        db.session.commit()
        return ok({"scheduled": True, "effective": sub.current_period_end.isoformat() if sub.current_period_end else None})
    res = core.start_checkout(ws, g.user, d.plan_key, d.interval, d.coupon_code)
    db.session.commit()
    return ok(res)


class MockComplete(Schema):
    session_id: str
    outcome: str = Field(default="success", pattern="^(success|failure)$")
    card_last4: str | None = Field(default=None, max_length=4)


@bp.post("/billing/mock/complete")
@protect("billing.manage", allow_restricted=True)
def mock_complete():
    """Simulated hosted checkout. Only exists for the mock provider; the card number never reaches the server."""
    from app.models import CheckoutSession
    from app.services.billing.types import BillingEvent

    if current_app.config["BILLING_PROVIDER"] != "mock":
        raise not_found("Endpoint")
    d = parse(MockComplete)
    cs = db.session.query(CheckoutSession).filter_by(provider_session_id=d.session_id, workspace_id=g.workspace.id).one_or_none()
    if cs is None or cs.status != "open":
        raise ApiError(409, "checkout_closed", "This checkout session is no longer open.")
    q = core.quote(g.workspace, cs.plan_key, cs.interval, cs.coupon_code)
    now = utcnow()
    import datetime as dt

    ev = BillingEvent(id=f"mock_ev_{cs.id}", type="payment_succeeded" if d.outcome == "success" else "payment_failed", workspace_id=str(g.workspace.id),
                      checkout_session_id=str(cs.id), provider_subscription_id=f"mock_sub_{g.workspace.id.hex[:12]}", provider_payment_id=f"mock_pay_{cs.id}",
                      amount=q["total"], currency=q["currency"], period_start=now, period_end=now + dt.timedelta(days=core.PERIOD[cs.interval]),
                      failure_reason="Your card was declined (simulated)", payment_method={"brand": "visa", "last4": d.card_last4 or "4242"})
    if d.outcome == "failure":
        cs.status = "failed"
        db.session.commit()
        raise ApiError(402, "payment_failed", "Your card was declined. Try a different payment method.")
    core.apply_event(ev, "mock")
    db.session.commit()
    return ok({"status": "active", "subscription": subscription_summary(g.workspace)})


@bp.get("/billing/checkout/<sid>")
@protect("billing.manage", allow_restricted=True)
def checkout_info(sid):
    from app.models import CheckoutSession

    cs = db.session.query(CheckoutSession).filter_by(provider_session_id=sid, workspace_id=g.workspace.id).one_or_none()
    if cs is None:
        raise not_found("Checkout session")
    return ok({"status": cs.status, "provider": cs.provider, "quote": core.quote(g.workspace, cs.plan_key, cs.interval, cs.coupon_code)})


class CancelIn(Schema):
    immediately: bool = False
    reason: str | None = Field(default=None, max_length=300)


@bp.post("/billing/cancel")
@protect("billing.manage", allow_restricted=True)
def cancel():
    d = parse(CancelIn)
    core.cancel(g.workspace, d.immediately)
    if d.reason:
        analytics.track("cancel_reason", {"reason": d.reason})
    db.session.commit()
    return ok(subscription_summary(g.workspace))


@bp.post("/billing/resume")
@protect("billing.manage", allow_restricted=True)
def resume():
    core.resume(g.workspace)
    db.session.commit()
    return ok(subscription_summary(g.workspace))


@bp.post("/billing/cancel-downgrade")
@protect("billing.manage", allow_restricted=True)
def cancel_downgrade():
    sub = core.active_subscription(g.workspace)
    if sub:
        sub.pending_plan_key = sub.pending_interval = None
        db.session.commit()
    return ok({"ok": True})


@bp.get("/billing/invoices")
@protect("billing.manage", allow_restricted=True)
def invoices():
    rows = db.session.query(Invoice).filter_by(workspace_id=g.workspace.id).order_by(Invoice.created_at.desc()).limit(100).all()
    return ok([r.to_dict() for r in rows])


@bp.get("/billing/payments")
@protect("billing.manage", allow_restricted=True)
def payments():
    rows = db.session.query(Payment).filter_by(workspace_id=g.workspace.id).order_by(Payment.created_at.desc()).limit(100).all()
    return ok([r.to_dict(exclude=("provider_payment_id",)) for r in rows])


@bp.get("/billing/invoices/<uuid:iid>/pdf")
@protect("billing.manage", allow_restricted=True)
def invoice_pdf(iid):
    inv = db.session.query(Invoice).filter_by(id=iid, workspace_id=g.workspace.id).one_or_none()
    if inv is None:
        raise not_found("Invoice")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=inv.number)
    st = getSampleStyleSheet()
    money = lambda v: f"{inv.currency} {v / 100:,.2f}"  # noqa: E731
    els = [Paragraph("CRM Wala", st["Title"]), Paragraph(f"Invoice {inv.number}", st["Heading2"]),
           Paragraph(f"Billed to: {g.workspace.name}<br/>Date: {inv.created_at:%d %b %Y}<br/>Period: {inv.period_start:%d %b %Y} – {inv.period_end:%d %b %Y}" if inv.period_start else f"Billed to: {g.workspace.name}", st["Normal"]),
           Spacer(1, 18)]
    rows = [["Description", "Amount"]] + [[li["description"], money(li["amount"])] for li in inv.line_items]
    if inv.discount:
        rows.append(["Discount", "-" + money(inv.discount)])
    rows.append([f"{inv.billing_details.get('tax_name', 'Tax')} ({inv.billing_details.get('tax_percent', 0)}%)", money(inv.tax)])
    rows.append(["Total paid", money(inv.total)])
    t = Table(rows, colWidths=[360, 120])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                           ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0"))]))
    els.append(t)
    doc.build(els)
    return Response(buf.getvalue(), mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="{inv.number}.pdf"'})


class SalesIn(Schema):
    message: str = Field(min_length=1, max_length=2000)
    seats: int | None = None


@bp.post("/billing/contact-sales")
@protect("billing.manage", allow_restricted=True)
def contact_sales():
    d = parse(SalesIn)
    analytics.track("enterprise_inquiry", {"message": d.message[:500], "seats": d.seats})
    audit.record("billing.enterprise_inquiry", entity_type="workspace", entity_id=g.workspace.id, summary="Enterprise inquiry submitted", after={"message": d.message[:500]})
    db.session.commit()
    return ok({"received": True})


# ---- provider webhooks (public, signature-verified, idempotent) -------------------------

@bp.post("/billing/webhooks/<provider>")
def webhook(provider):
    if provider not in ("stripe", "razorpay"):
        raise not_found("Provider")
    if current_app.config["BILLING_PROVIDER"] != provider:
        raise ApiError(409, "provider_inactive", "This provider is not the active billing provider")
    body = request.get_data()
    with bypass_scope():
        events = get_provider(provider).parse_webhook(request.headers, body)
        for ev in events:
            if db.session.query(WebhookEvent).filter_by(provider=provider, event_id=ev.id).first():
                continue
            row = WebhookEvent(provider=provider, event_id=ev.id, event_type=ev.type, payload={"workspace_id": ev.workspace_id, "amount": ev.amount})
            db.session.add(row)
            db.session.flush()
            try:
                outcome = core.apply_event(ev, provider)
                row.status, row.processed_at = ("ignored" if outcome.startswith("ignored") else "processed"), utcnow()
            except Exception as e:  # recorded for the admin "payment webhook status" view; provider will retry on 5xx
                db.session.rollback()
                db.session.add(WebhookEvent(provider=provider, event_id=ev.id + ":failed", event_type=ev.type, status="failed", error=str(e)[:500]))
                db.session.commit()
                raise
        db.session.commit()
    return ok({"received": len(events)})
