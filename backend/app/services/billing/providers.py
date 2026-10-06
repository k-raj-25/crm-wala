"""Billing provider interface + implementations. Cards are collected on the provider's hosted page;
we never see or store PAN/CVV. Swap provider with BILLING_PROVIDER=mock|stripe|razorpay."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import uuid
from typing import Protocol

import httpx
from flask import current_app

from app.core.errors import ApiError, bad_request
from app.models import CheckoutSession, Subscription, Workspace
from app.services.billing.types import BillingEvent, CheckoutResult


class BillingProvider(Protocol):
    name: str

    def create_checkout(self, ws: Workspace, cs: CheckoutSession, plan_name: str, customer_email: str) -> CheckoutResult: ...
    def cancel(self, sub: Subscription, at_period_end: bool) -> None: ...
    def resume(self, sub: Subscription) -> None: ...
    def parse_webhook(self, headers, body: bytes) -> list[BillingEvent]: ...


class MockProvider:
    """Fully working local provider: hosted-checkout simulation + the same event pipeline as real providers."""

    name = "mock"

    def create_checkout(self, ws, cs, plan_name, customer_email):
        sid = f"mock_cs_{uuid.uuid4().hex[:16]}"
        return CheckoutResult(sid, f"{current_app.config['WEB_ORIGIN']}/app/billing/checkout?session={sid}")

    def cancel(self, sub, at_period_end):
        return None

    def resume(self, sub):
        return None

    def parse_webhook(self, headers, body):
        raise bad_request("The mock provider has no webhooks", "no_webhooks")


def _ts(v) -> dt.datetime | None:
    return dt.datetime.fromtimestamp(v, dt.timezone.utc) if v else None


class StripeProvider:
    name = "stripe"

    def __init__(self) -> None:
        import stripe

        self.stripe = stripe
        stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]

    def create_checkout(self, ws, cs, plan_name, customer_email):
        interval = "year" if cs.interval == "annual" else "month"
        session = self.stripe.checkout.Session.create(
            mode="subscription", customer_email=customer_email if not ws.provider_customer_id else None,
            customer=ws.provider_customer_id or None, client_reference_id=str(cs.id),
            line_items=[{"quantity": 1, "price_data": {"currency": cs.currency.lower(), "unit_amount": cs.amount,
                                                       "recurring": {"interval": interval}, "product_data": {"name": f"CRM Wala {plan_name}"}}}],
            metadata={"workspace_id": str(ws.id), "checkout_session_id": str(cs.id)},
            subscription_data={"metadata": {"workspace_id": str(ws.id), "checkout_session_id": str(cs.id)}},
            success_url=f"{current_app.config['WEB_ORIGIN']}/app/billing?checkout=success",
            cancel_url=f"{current_app.config['WEB_ORIGIN']}/app/billing?checkout=canceled",
        )
        return CheckoutResult(session.id, session.url)

    def cancel(self, sub, at_period_end):
        if at_period_end:
            self.stripe.Subscription.modify(sub.provider_subscription_id, cancel_at_period_end=True)
        else:
            self.stripe.Subscription.cancel(sub.provider_subscription_id)

    def resume(self, sub):
        self.stripe.Subscription.modify(sub.provider_subscription_id, cancel_at_period_end=False)

    def parse_webhook(self, headers, body):
        try:
            event = self.stripe.Webhook.construct_event(body, headers.get("Stripe-Signature", ""), current_app.config["STRIPE_WEBHOOK_SECRET"])
        except Exception:
            raise ApiError(400, "invalid_signature", "Invalid webhook signature")
        obj = event["data"]["object"]
        t = event["type"]
        meta = obj.get("metadata") or {}
        if t == "checkout.session.completed" and obj.get("mode") == "subscription":
            return [BillingEvent(id=event["id"], type="checkout_completed", workspace_id=meta.get("workspace_id"), checkout_session_id=meta.get("checkout_session_id"),
                                 provider_subscription_id=obj.get("subscription"), raw={"customer": obj.get("customer")})]
        if t == "invoice.paid":
            line = (obj.get("lines") or {}).get("data", [{}])[0]
            sub_meta = (obj.get("subscription_details") or {}).get("metadata") or {}
            return [BillingEvent(id=event["id"], type="payment_succeeded", workspace_id=sub_meta.get("workspace_id"), checkout_session_id=sub_meta.get("checkout_session_id"),
                                 provider_subscription_id=obj.get("subscription"), provider_payment_id=obj.get("payment_intent") or obj.get("id"),
                                 amount=obj.get("amount_paid", 0), currency=(obj.get("currency") or "inr").upper(),
                                 period_start=_ts((line.get("period") or {}).get("start")), period_end=_ts((line.get("period") or {}).get("end")))]
        if t == "invoice.payment_failed":
            sub_meta = (obj.get("subscription_details") or {}).get("metadata") or {}
            return [BillingEvent(id=event["id"], type="payment_failed", workspace_id=sub_meta.get("workspace_id"), provider_subscription_id=obj.get("subscription"),
                                 provider_payment_id=obj.get("payment_intent") or obj.get("id"), amount=obj.get("amount_due", 0), currency=(obj.get("currency") or "inr").upper(),
                                 failure_reason="Payment was declined")]
        if t == "customer.subscription.deleted":
            return [BillingEvent(id=event["id"], type="subscription_canceled", workspace_id=(obj.get("metadata") or {}).get("workspace_id"), provider_subscription_id=obj.get("id"))]
        return []


class RazorpayProvider:
    """Razorpay Subscriptions via REST. Plans are created on the fly so Super Admin pricing stays dynamic."""

    name = "razorpay"
    base = "https://api.razorpay.com/v1"

    def _auth(self):
        c = current_app.config
        return (c["RAZORPAY_KEY_ID"], c["RAZORPAY_KEY_SECRET"])

    def _post(self, path, payload):
        r = httpx.post(f"{self.base}{path}", json=payload, auth=self._auth(), timeout=20)
        if r.status_code >= 400:
            raise ApiError(502, "provider_error", "The payment provider rejected the request. Please try again.", {"provider": r.text[:300]})
        return r.json()

    def create_checkout(self, ws, cs, plan_name, customer_email):
        period = "yearly" if cs.interval == "annual" else "monthly"
        plan = self._post("/plans", {"period": period, "interval": 1, "item": {"name": f"CRM Wala {plan_name} ({period})", "amount": cs.amount, "currency": cs.currency}})
        sub = self._post("/subscriptions", {"plan_id": plan["id"], "total_count": 120 if period == "monthly" else 10, "customer_notify": 1,
                                            "notes": {"workspace_id": str(ws.id), "checkout_session_id": str(cs.id)}})
        return CheckoutResult(sub["id"], sub["short_url"])

    def cancel(self, sub, at_period_end):
        self._post(f"/subscriptions/{sub.provider_subscription_id}/cancel", {"cancel_at_cycle_end": 1 if at_period_end else 0})

    def resume(self, sub):
        raise ApiError(409, "not_supported", "Start a new subscription to resume.")

    def parse_webhook(self, headers, body):
        expected = hmac.new(current_app.config["RAZORPAY_WEBHOOK_SECRET"].encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, headers.get("X-Razorpay-Signature", "")):
            raise ApiError(400, "invalid_signature", "Invalid webhook signature")
        payload = json.loads(body)
        t, eid = payload.get("event", ""), headers.get("X-Razorpay-Event-Id") or hashlib.sha256(body).hexdigest()
        sub = (payload.get("payload", {}).get("subscription", {}) or {}).get("entity", {})
        pay = (payload.get("payload", {}).get("payment", {}) or {}).get("entity", {})
        notes = sub.get("notes") or pay.get("notes") or {}
        if t == "subscription.charged":
            return [BillingEvent(id=eid, type="payment_succeeded", workspace_id=notes.get("workspace_id"), checkout_session_id=notes.get("checkout_session_id"),
                                 provider_subscription_id=sub.get("id"), provider_payment_id=pay.get("id"), amount=pay.get("amount", 0), currency=pay.get("currency", "INR"),
                                 period_start=_ts(sub.get("current_start")), period_end=_ts(sub.get("current_end")),
                                 payment_method={"brand": pay.get("method"), "last4": (pay.get("card") or {}).get("last4")})]
        if t == "payment.failed":
            return [BillingEvent(id=eid, type="payment_failed", workspace_id=notes.get("workspace_id"), provider_subscription_id=pay.get("subscription_id") or sub.get("id"),
                                 provider_payment_id=pay.get("id"), amount=pay.get("amount", 0), currency=pay.get("currency", "INR"), failure_reason=pay.get("error_description"))]
        if t in ("subscription.cancelled", "subscription.completed"):
            return [BillingEvent(id=eid, type="subscription_canceled", workspace_id=notes.get("workspace_id"), provider_subscription_id=sub.get("id"))]
        return []


PROVIDERS = {"mock": MockProvider, "stripe": StripeProvider, "razorpay": RazorpayProvider}


def get_provider(name: str | None = None) -> BillingProvider:
    name = name or current_app.config["BILLING_PROVIDER"]
    if name not in PROVIDERS:
        raise ApiError(500, "provider_misconfigured", "Billing provider is not configured")
    return PROVIDERS[name]()
