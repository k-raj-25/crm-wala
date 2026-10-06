from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class CheckoutResult:
    provider_session_id: str
    url: str


@dataclass
class BillingEvent:
    """Provider-neutral webhook event. Every provider maps its payloads to these."""

    id: str
    type: str  # payment_succeeded | payment_failed | subscription_canceled | refund
    workspace_id: str | None = None
    checkout_session_id: str | None = None  # our CheckoutSession.id
    provider_subscription_id: str | None = None
    provider_payment_id: str | None = None
    amount: int = 0
    currency: str = "INR"
    period_start: dt.datetime | None = None
    period_end: dt.datetime | None = None
    failure_reason: str | None = None
    payment_method: dict = field(default_factory=dict)  # brand/last4 only
    raw: dict = field(default_factory=dict)
