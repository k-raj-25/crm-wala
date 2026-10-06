from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    ARRAY, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base
from app.models.base import Serializable, Timestamps, UUIDPk


class Plan(Base, UUIDPk, Timestamps, Serializable):
    """Fully admin-configurable. Prices are integer minor units (paise/cents)."""

    __tablename__ = "plans"

    key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    price_monthly: Mapped[int | None] = mapped_column(Integer)  # NULL => custom pricing (Enterprise)
    price_annual: Mapped[int | None] = mapped_column(Integer)
    limits: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    # limits: users, contacts, pipelines, automations, ai_actions_month, storage_mb, emails_month  (null = unlimited)
    features: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    highlights: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    provider_price_ids: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))


class Coupon(Base, UUIDPk, Timestamps, Serializable):
    __tablename__ = "coupons"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200))
    percent_off: Mapped[int | None] = mapped_column(Integer)
    amount_off: Mapped[int | None] = mapped_column(Integer)  # minor units
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    duration: Mapped[str] = mapped_column(String(20), default="once", server_default="once")  # once|forever|repeating
    duration_months: Mapped[int | None] = mapped_column(Integer)
    max_redemptions: Mapped[int | None] = mapped_column(Integer)
    times_redeemed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    valid_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    plan_keys: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Subscription(Base, UUIDPk, Timestamps, Serializable):
    __tablename__ = "subscriptions"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    plan_key: Mapped[str] = mapped_column(String(40), nullable=False)
    interval: Mapped[str] = mapped_column(String(10), default="monthly")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|past_due|canceled|ended
    amount: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    coupon_code: Mapped[str | None] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(20), default="mock")
    provider_subscription_id: Mapped[str | None] = mapped_column(String(120), index=True)
    current_period_start: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    canceled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    pending_plan_key: Mapped[str | None] = mapped_column(String(40))  # scheduled downgrade
    pending_interval: Mapped[str | None] = mapped_column(String(10))
    payment_method: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    # payment_method holds only provider tokens + display metadata (brand/last4), never PAN/CVV


class Payment(Base, UUIDPk, Timestamps, Serializable):
    __tablename__ = "payments"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subscriptions.id", ondelete="SET NULL"))
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20))  # succeeded|failed|refunded|pending
    provider: Mapped[str] = mapped_column(String(20), default="mock")
    provider_payment_id: Mapped[str | None] = mapped_column(String(120), index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(300))
    refunded_amount: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    description: Mapped[str | None] = mapped_column(String(200))


class Invoice(Base, UUIDPk, Timestamps, Serializable):
    __tablename__ = "invoices"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"))
    number: Mapped[str] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="paid")  # paid|open|void
    subtotal: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer, default=0)
    tax: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    line_items: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    period_start: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    billing_details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))


class CouponRedemption(Base, UUIDPk, Timestamps):
    __tablename__ = "coupon_redemptions"
    __table_args__ = (UniqueConstraint("coupon_id", "workspace_id", name="uq_coupon_ws"),)

    coupon_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coupons.id", ondelete="CASCADE"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))


class CheckoutSession(Base, UUIDPk, Timestamps):
    __tablename__ = "checkout_sessions"

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    plan_key: Mapped[str] = mapped_column(String(40))
    interval: Mapped[str] = mapped_column(String(10))
    coupon_code: Mapped[str | None] = mapped_column(String(40))
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    provider: Mapped[str] = mapped_column(String(20))
    provider_session_id: Mapped[str | None] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|completed|expired|failed
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class WebhookEvent(Base, UUIDPk, Timestamps, Serializable):
    """Idempotency + observability for payment webhooks."""

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)

    provider: Mapped[str] = mapped_column(String(20))
    event_id: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="received")  # received|processed|failed|ignored
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    processed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformSetting(Base, Timestamps, Serializable):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    description: Mapped[str | None] = mapped_column(String(300))


class FeatureFlag(Base, Timestamps, Serializable):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    rollout_percent: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    workspace_overrides: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    # {workspace_id: true|false}
