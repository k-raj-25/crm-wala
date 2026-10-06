from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import (
    ARRAY, BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.extensions import Base
from app.models.base import Serializable, SoftDelete, Tenant, Timestamps, UUIDPk


class Related:
    """Optional links to the primary CRM entities (used by tasks, notes, calls, meetings, emails, files, activities)."""

    @declared_attr
    def lead_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), index=True)

    @declared_attr
    def contact_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), index=True)

    @declared_attr
    def company_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True)

    @declared_attr
    def deal_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), index=True)


class Pipeline(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Serializable):
    __tablename__ = "pipelines"

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")

    stages: Mapped[list["PipelineStage"]] = relationship(
        back_populates="pipeline", order_by="PipelineStage.position", cascade="all, delete-orphan"
    )


class PipelineStage(Base, UUIDPk, Timestamps, Tenant, Serializable):
    __tablename__ = "pipeline_stages"

    pipeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    probability: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(10), default="open", server_default="open")  # open|won|lost
    color: Mapped[str | None] = mapped_column(String(9))

    pipeline: Mapped[Pipeline] = relationship(back_populates="stages")


class Company(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Serializable):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    website: Mapped[str | None] = mapped_column(String(300))
    domain: Mapped[str | None] = mapped_column(String(200), index=True)
    industry: Mapped[str | None] = mapped_column(String(80))
    size: Mapped[str | None] = mapped_column(String(40))
    location: Mapped[str | None] = mapped_column(String(160))
    annual_revenue: Mapped[decimal.Decimal | None] = mapped_column(Numeric(16, 2))
    phone: Mapped[str | None] = mapped_column(String(40))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    description: Mapped[str | None] = mapped_column(Text)
    custom: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    last_activity_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Contact(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Serializable):
    __tablename__ = "contacts"

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(254), index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    job_title: Mapped[str | None] = mapped_column(String(120))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), index=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(160))
    socials: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    description: Mapped[str | None] = mapped_column(Text)
    custom: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    source_lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    last_contacted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    company: Mapped[Company | None] = relationship(lazy="joined")

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name or ''}".strip()


class Lead(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Serializable):
    __tablename__ = "leads"

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(254), index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    company_name: Mapped[str | None] = mapped_column(String(200))
    job_title: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default="new", server_default="new", index=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    score: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    score_reasons: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    location: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    custom: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    last_contacted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_up_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_activity_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    converted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    converted_contact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    converted_deal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lost_reason: Mapped[str | None] = mapped_column(String(200))

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name or ''}".strip()


class Deal(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Serializable):
    __tablename__ = "deals"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), index=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    pipeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipelines.id"), index=True)
    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_stages.id"), index=True)
    value: Mapped[decimal.Decimal] = mapped_column(Numeric(16, 2), default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    probability: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    priority: Mapped[str] = mapped_column(String(10), default="medium", server_default="medium")
    expected_close_date: Mapped[dt.date | None] = mapped_column(Date, index=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    source: Mapped[str | None] = mapped_column(String(60))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    description: Mapped[str | None] = mapped_column(Text)
    custom: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(10), default="open", server_default="open", index=True)  # open|won|lost
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    lost_reason: Mapped[str | None] = mapped_column(String(200))
    stage_entered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    position: Mapped[float] = mapped_column(Numeric(20, 6), default=0, server_default="0")  # order within stage
    lead_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_activity_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company | None] = relationship(lazy="joined")
    contact: Mapped[Contact | None] = relationship(lazy="joined")
    stage: Mapped[PipelineStage] = relationship(lazy="joined")


Index("ix_deals_ws_stage_pos", Deal.workspace_id, Deal.stage_id, Deal.position)


class Task(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Related, Serializable):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    due_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium", server_default="medium")
    status: Mapped[str] = mapped_column(String(15), default="todo", server_default="todo", index=True)
    kind: Mapped[str] = mapped_column(String(20), default="task", server_default="task")  # task|follow_up|deadline
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    position: Mapped[float] = mapped_column(Numeric(20, 6), default=0, server_default="0")


class Note(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Related, Serializable):
    __tablename__ = "notes"

    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    mentions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))


class Call(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Related, Serializable):
    __tablename__ = "calls"

    direction: Mapped[str] = mapped_column(String(10), default="outbound")
    status: Mapped[str] = mapped_column(String(15), default="completed")  # scheduled|completed|canceled
    outcome: Mapped[str | None] = mapped_column(String(30))
    # connected|no_answer|follow_up_required|interested|not_interested
    phone: Mapped[str | None] = mapped_column(String(40))
    scheduled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    occurred_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    provider: Mapped[str | None] = mapped_column(String(30))  # telephony integration hook
    provider_call_id: Mapped[str | None] = mapped_column(String(120))
    recording_url: Mapped[str | None] = mapped_column(String(500))


class Meeting(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Related, Serializable):
    __tablename__ = "meetings"

    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(300))
    meeting_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(15), default="scheduled", server_default="scheduled")
    attendees: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    organizer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    summary: Mapped[str | None] = mapped_column(Text)
    external_event_id: Mapped[str | None] = mapped_column(String(200))
    reminder_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Email(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Related, Serializable):
    __tablename__ = "emails"

    direction: Mapped[str] = mapped_column(String(10), default="outbound")
    status: Mapped[str] = mapped_column(String(15), default="sent", index=True)  # draft|scheduled|sent|failed|received
    subject: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    from_address: Mapped[str | None] = mapped_column(String(254))
    to_addresses: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    cc_addresses: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    scheduled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    tracking_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    opens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    clicks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_opened_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    thread_id: Mapped[str | None] = mapped_column(String(120), index=True)
    provider: Mapped[str | None] = mapped_column(String(30))
    provider_message_id: Mapped[str | None] = mapped_column(String(300))
    attachment_file_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    error: Mapped[str | None] = mapped_column(String(300))


class EmailTemplate(Base, UUIDPk, Timestamps, Tenant, Serializable):
    __tablename__ = "crm_email_templates"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class FileAsset(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Related, Serializable):
    __tablename__ = "files"
    __hidden__ = ("storage_key",)

    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(15), default="ready", server_default="ready")  # pending|ready


class Activity(Base, UUIDPk, Tenant, Related, Serializable):
    """Immutable timeline events shown on every entity."""

    __tablename__ = "activities"

    type: Mapped[str] = mapped_column(String(30), index=True)
    # created|updated|stage_changed|status_changed|note|email|call|meeting|task|task_completed|converted|file|assigned|won|lost|system
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True, server_default=text("now()"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


Index("ix_activities_ws_occurred", Activity.workspace_id, Activity.occurred_at.desc())


class Tag(Base, UUIDPk, Timestamps, Tenant, Serializable):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_tag_ws_name"),)

    name: Mapped[str] = mapped_column(String(40), nullable=False)
    color: Mapped[str | None] = mapped_column(String(9))


class CustomFieldDef(Base, UUIDPk, Timestamps, Tenant, Serializable):
    __tablename__ = "custom_field_defs"
    __table_args__ = (UniqueConstraint("workspace_id", "entity_type", "key", name="uq_cf_ws_entity_key"),)

    entity_type: Mapped[str] = mapped_column(String(20))  # lead|contact|company|deal
    key: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(100))
    field_type: Mapped[str] = mapped_column(String(20))
    # text|number|currency|date|dropdown|multi_select|checkbox|url|email|phone
    options: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class SavedView(Base, UUIDPk, Timestamps, Tenant, Serializable):
    __tablename__ = "saved_views"

    entity_type: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(80))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    shared: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    filters: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    sort: Mapped[str | None] = mapped_column(String(60))
    columns: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))


class DuplicateDismissal(Base, UUIDPk, Timestamps, Tenant):
    __tablename__ = "duplicate_dismissals"
    __table_args__ = (UniqueConstraint("workspace_id", "entity_type", "a_id", "b_id", name="uq_dup_pair"),)

    entity_type: Mapped[str] = mapped_column(String(20))
    a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
