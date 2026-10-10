from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any, Literal

from pydantic import Field, field_validator

from app.schemas.common import Email, Schema, patchify

Priority = Literal["low", "medium", "high", "urgent"]
Tags = list[str]


def _clean_tags(v: list[str] | None) -> list[str]:
    seen: list[str] = []
    for t in v or []:
        t = t.strip()[:40]
        if t and t not in seen:
            seen.append(t)
    return seen[:25]


class _Tagged(Schema):
    tags: Tags = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        return _clean_tags(v)


class LeadIn(_Tagged):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: Email | None = None
    phone: str | None = Field(default=None, max_length=40)
    company_name: str | None = Field(default=None, max_length=200)
    job_title: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, max_length=60)
    status: str = "new"
    owner_id: uuid.UUID | None = None
    location: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=10000)
    custom: dict[str, Any] = Field(default_factory=dict)
    next_follow_up_at: dt.datetime | None = None
    last_contacted_at: dt.datetime | None = None
    intent: Literal["buy", "rent", "invest", "sell", "lease"] | None = None
    property_type: Literal["apartment", "villa", "plot", "office", "shop", "other"] | None = None
    bhk: str | None = Field(default=None, max_length=20)
    budget_min: decimal.Decimal | None = Field(default=None, ge=0)
    budget_max: decimal.Decimal | None = Field(default=None, ge=0)
    project_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None


LeadPatch = patchify(LeadIn, "LeadPatch")


class ContactIn(_Tagged):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: Email | None = None
    phone: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=120)
    company_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    location: str | None = Field(default=None, max_length=160)
    socials: dict[str, str] = Field(default_factory=dict)
    description: str | None = Field(default=None, max_length=10000)
    custom: dict[str, Any] = Field(default_factory=dict)
    avatar_url: str | None = Field(default=None, max_length=500)
    last_contacted_at: dt.datetime | None = None

    @field_validator("socials")
    @classmethod
    def _socials(cls, v):
        allowed = {"linkedin", "twitter", "facebook", "instagram", "github", "website", "whatsapp"}
        return {k: str(x)[:300] for k, x in v.items() if k in allowed and x}


ContactPatch = patchify(ContactIn, "ContactPatch")


class CompanyIn(_Tagged):
    name: str = Field(min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=300)
    industry: str | None = Field(default=None, max_length=80)
    size: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=160)
    annual_revenue: decimal.Decimal | None = Field(default=None, ge=0)
    phone: str | None = Field(default=None, max_length=40)
    owner_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=10000)
    custom: dict[str, Any] = Field(default_factory=dict)


CompanyPatch = patchify(CompanyIn, "CompanyPatch")


class DealIn(_Tagged):
    name: str = Field(min_length=1, max_length=200)
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    pipeline_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    value: decimal.Decimal = Field(default=decimal.Decimal(0), ge=0, le=decimal.Decimal("999999999999"))
    currency: str = Field(default="INR", min_length=3, max_length=3)
    probability: int | None = Field(default=None, ge=0, le=100)
    priority: Priority = "medium"
    expected_close_date: dt.date | None = None
    owner_id: uuid.UUID | None = None
    source: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=10000)
    custom: dict[str, Any] = Field(default_factory=dict)
    unit_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


DealPatch = patchify(DealIn, "DealPatch")


class TaskIn(Schema):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=10000)
    assignee_id: uuid.UUID | None = None
    due_at: dt.datetime | None = None
    priority: Priority = "medium"
    status: Literal["todo", "in_progress", "completed"] = "todo"
    kind: Literal["task", "follow_up", "deadline"] = "task"
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None


TaskPatch = patchify(TaskIn, "TaskPatch")


class NoteIn(Schema):
    body: str = Field(min_length=1, max_length=20000)
    pinned: bool = False
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None


NotePatch = patchify(NoteIn, "NotePatch")


class CallIn(Schema):
    direction: Literal["inbound", "outbound"] = "outbound"
    status: Literal["scheduled", "completed", "canceled"] = "completed"
    outcome: Literal["connected", "no_answer", "follow_up_required", "interested", "not_interested"] | None = None
    phone: str | None = Field(default=None, max_length=40)
    scheduled_at: dt.datetime | None = None
    occurred_at: dt.datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    notes: str | None = Field(default=None, max_length=10000)
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None


CallPatch = patchify(CallIn, "CallPatch")


class MeetingIn(Schema):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=10000)
    starts_at: dt.datetime
    ends_at: dt.datetime
    location: str | None = Field(default=None, max_length=300)
    meeting_url: str | None = Field(default=None, max_length=500)
    status: Literal["scheduled", "completed", "canceled"] = "scheduled"
    attendees: list[dict[str, Any]] = Field(default_factory=list)
    summary: str | None = Field(default=None, max_length=20000)
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    kind: Literal["meeting", "site_visit"] = "meeting"
    project_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None

    @field_validator("ends_at")
    @classmethod
    def _after(cls, v, info):
        s = info.data.get("starts_at")
        if s and v <= s:
            raise ValueError("End time must be after the start time")
        return v

    @field_validator("attendees")
    @classmethod
    def _att(cls, v):
        return [{"name": str(a.get("name", ""))[:120], "email": str(a.get("email", ""))[:254]} for a in v[:50]]


MeetingPatch = patchify(MeetingIn, "MeetingPatch")


class EmailSendIn(Schema):
    to: list[Email] = Field(min_length=1, max_length=20)
    cc: list[Email] = Field(default_factory=list, max_length=20)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=100000)
    scheduled_at: dt.datetime | None = None
    track: bool = True
    attachment_file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None


class EmailLogIn(Schema):
    """Manually log an email that happened outside the CRM (or an inbound one)."""

    direction: Literal["inbound", "outbound"] = "inbound"
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=100000)
    from_address: Email | None = None
    to_addresses: list[Email] = Field(default_factory=list)
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None


class EmailTemplateIn(Schema):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=100000)
