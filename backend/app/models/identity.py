from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    ARRAY, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Base
from app.models.base import Serializable, SoftDelete, Timestamps, UUIDPk, utcnow


class User(Base, UUIDPk, Timestamps, SoftDelete, Serializable):
    __tablename__ = "users"
    __hidden__ = ("password_hash", "totp_secret_enc", "failed_login_count", "locked_until")

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    job_role: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))
    email_verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")  # active|suspended
    suspended_reason: Mapped[str | None] = mapped_column(String(300))
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_ip: Mapped[str | None] = mapped_column(String(64))
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    # preferences: theme, date_format, currency, timezone, locale, default_pipeline_id, dashboard_widgets, notifications


class UserSession(Base, UUIDPk, Timestamps):
    """Server-side refresh-token sessions (rotation + revocation + device list)."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    impersonator_admin_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Workspace(Base, UUIDPk, Timestamps, SoftDelete, Serializable):
    __tablename__ = "workspaces"
    __hidden__ = ("provider_customer_id",)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    brand_color: Mapped[str | None] = mapped_column(String(9))
    industry: Mapped[str | None] = mapped_column(String(80))
    company_size: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(300))
    sales_model: Mapped[str | None] = mapped_column(String(40))
    goals: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", server_default="Asia/Kolkata")
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    locale: Mapped[str] = mapped_column(String(10), default="en", server_default="en")
    onboarding_completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    onboarding_state: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    # settings: lead_statuses, notification defaults, public_form_token, branding, ...
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")  # active|suspended

    # Billing state (denormalised for fast gating; subscriptions table is the ledger)
    plan_key: Mapped[str] = mapped_column(String(40), default="trial", server_default="trial")
    subscription_status: Mapped[str] = mapped_column(String(20), default="trialing", server_default="trialing")
    # trialing | active | past_due | canceled | expired
    billing_interval: Mapped[str | None] = mapped_column(String(10))
    trial_started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    grace_ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    provider_customer_id: Mapped[str | None] = mapped_column(String(120))
    credit_balance: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # minor units
    limit_overrides: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    last_activity_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    trial_milestones_sent: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))

    owner: Mapped[User] = relationship(foreign_keys=[owner_id])


class Role(Base, UUIDPk, Timestamps, Serializable):
    """System roles have workspace_id NULL; custom roles belong to one workspace."""

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("workspace_id", "key", name="uq_roles_ws_key"),)

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    rank: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # higher = more privileged


Index("uq_roles_system_key", Role.key, unique=True, postgresql_where=text("workspace_id IS NULL"))


class Permission(Base, Serializable):
    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    group: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)


class WorkspaceMember(Base, UUIDPk, Timestamps, Serializable):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_member_ws_user"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")  # active|disabled
    notification_prefs: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()
    role: Mapped[Role] = relationship()


class Team(Base, UUIDPk, Timestamps, Serializable):
    __tablename__ = "teams"
    __tenant__ = True

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))


class Invitation(Base, UUIDPk, Timestamps, Serializable):
    __tablename__ = "invitations"
    __hidden__ = ("token_hash",)

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    role: Mapped[Role] = relationship()


class AdminUser(Base, UUIDPk, Timestamps, Serializable):
    """Platform operators. Completely separate from `users`; never share credentials or tokens."""

    __tablename__ = "admin_users"
    __hidden__ = ("password_hash", "totp_secret_enc", "failed_login_count", "locked_until")

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="superadmin", server_default="superadmin")  # superadmin|support|finance
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_ip: Mapped[str | None] = mapped_column(String(64))


class AdminSession(Base, UUIDPk, Timestamps):
    __tablename__ = "admin_sessions"

    admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class ImpersonationGrant(Base, UUIDPk, Timestamps):
    """One-time code exchanged by the customer app to start an impersonated session."""

    __tablename__ = "impersonation_grants"

    admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin_users.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    reason: Mapped[str] = mapped_column(String(300))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
