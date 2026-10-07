from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    ARRAY, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base
from app.models.base import Serializable, SoftDelete, Tenant, Timestamps, UUIDPk


class Notification(Base, UUIDPk, Timestamps, Tenant, Serializable):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    # new_lead|task_assigned|deal_update|mention|meeting_reminder|automation|payment_issue|trial_ending|system
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(String(500))
    link: Mapped[str | None] = mapped_column(String(300))
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))


Index("ix_notifications_user_unread", Notification.user_id, Notification.read_at)


class AuditLog(Base, UUIDPk, Serializable):
    """Append-only. Not tenant-RLS'd: admins and workspace owners read it through scoped APIs."""

    __tablename__ = "audit_logs"

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), index=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_type: Mapped[str] = mapped_column(String(10), default="user")  # user|admin|system
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_label: Mapped[str | None] = mapped_column(String(200))
    impersonator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(String(400))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class AnalyticsEvent(Base, UUIDPk, Serializable):
    __tablename__ = "analytics_events"

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), index=True)
    name: Mapped[str] = mapped_column(String(60), index=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))


Index("ix_analytics_name_created", AnalyticsEvent.name, AnalyticsEvent.created_at)


class AiUsage(Base, UUIDPk, Tenant, Serializable):
    __tablename__ = "ai_usage"

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    feature: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(60))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)


class AiConversation(Base, UUIDPk, Timestamps, Tenant, Serializable):
    __tablename__ = "ai_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="New chat")
    messages: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))


class Integration(Base, UUIDPk, Timestamps, Tenant, Serializable):
    __tablename__ = "integrations"
    # Uniqueness is (workspace, provider, connecting user) via a COALESCE index created in migration 0004.
    __hidden__ = ("credentials_enc",)

    provider: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="not_connected")
    # not_connected|connected|error|reconnect
    mode: Mapped[str] = mapped_column(String(15), default="live")  # live|sandbox
    account_label: Mapped[str | None] = mapped_column(String(200))
    credentials_enc: Mapped[str | None] = mapped_column(Text)  # Fernet-encrypted JSON
    config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    last_synced_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(400))
    connected_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Automation(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Serializable):
    __tablename__ = "automations"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(400))
    trigger_type: Mapped[str] = mapped_column(String(40), index=True)
    trigger_config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    graph: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    # {nodes:[{id,type,data,position}], edges:[{id,source,target}]}
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    run_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AutomationRun(Base, UUIDPk, Timestamps, Tenant, Serializable):
    __tablename__ = "automation_runs"

    automation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automations.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(15), default="running", index=True)  # running|waiting|completed|failed
    trigger_payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    cursor_node_id: Mapped[str | None] = mapped_column(String(60))
    resume_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    steps: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class ImportJob(Base, UUIDPk, Timestamps, Tenant, Serializable):
    __tablename__ = "import_jobs"

    entity_type: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(15), default="completed")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    mapping: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    errors: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class SavedReport(Base, UUIDPk, Timestamps, Tenant, Serializable):
    __tablename__ = "saved_reports"

    name: Mapped[str] = mapped_column(String(120))
    report_type: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    schedule: Mapped[str | None] = mapped_column(String(15))  # daily|weekly|monthly
    recipients: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    last_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class EmailLog(Base, UUIDPk, Serializable):
    """Delivery log of platform (transactional) email, surfaced in Super Admin system health."""

    __tablename__ = "email_logs"

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), index=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    to_address: Mapped[str] = mapped_column(String(254))
    template_key: Mapped[str | None] = mapped_column(String(60))
    subject: Mapped[str] = mapped_column(String(300))
    provider: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(15))  # sent|failed|queued
    error: Mapped[str | None] = mapped_column(String(400))


class PlatformEmailTemplate(Base, Timestamps, Serializable):
    """Super-admin editable transactional templates."""

    __tablename__ = "platform_email_templates"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(300))
    body_html: Mapped[str] = mapped_column(Text)
    variables: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))


class JobLog(Base, UUIDPk, Serializable):
    """Background job runs (success/failure) for monitoring."""

    __tablename__ = "job_logs"

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), index=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(15))  # success|failed
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))


class ApiErrorLog(Base, UUIDPk, Serializable):
    __tablename__ = "api_error_logs"

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(300))
    status: Mapped[int] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    request_id: Mapped[str | None] = mapped_column(String(40))


class AuthEvent(Base, UUIDPk, Serializable):
    __tablename__ = "auth_events"

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), index=True)
    realm: Mapped[str] = mapped_column(String(10), default="user")  # user|admin
    event: Mapped[str] = mapped_column(String(40))  # login_success|login_failed|logout|lockout|password_reset|2fa_failed ...
    email: Mapped[str | None] = mapped_column(String(254))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class UserActivityDay(Base):
    """One row per user per active day. Powers DAU/WAU/MAU without logging every request."""

    __tablename__ = "user_activity_days"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    day: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
