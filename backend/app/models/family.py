"""Family and NRI mode: the people who decide on a home with the buyer (spouse, parents, a son working in Dubai)."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base
from app.models.base import Serializable, SoftDelete, Tenant, Timestamps, UUIDPk

__all__ = ["FamilyMember", "FamilyMessage", "Walkthrough"]


class FamilyMember(Base, UUIDPk, Timestamps, Tenant, SoftDelete, Serializable):
    """Someone in the buyer's family who decides, pays or advises. Stored on the lead, client or deal it was added on, and
    shown across the whole buyer (a son added while they were a lead is still there on the deal)."""

    __tablename__ = "family_members"
    __hidden__ = ("link_token",)

    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    relation: Mapped[str] = mapped_column(String(20), default="other", server_default="other")  # spouse|father|mother|son|daughter|...
    role: Mapped[str] = mapped_column(String(12), default="decides", server_default="decides")  # decides|pays|advises
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254))
    language: Mapped[str] = mapped_column(String(8), default="en", server_default="en")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", server_default="Asia/Kolkata")
    city: Mapped[str | None] = mapped_column(String(80))
    is_nri: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")  # INR|AED|USD
    checklist: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))  # item -> {"done_at", "by"}
    notes: Mapped[str | None] = mapped_column(Text)
    link_token: Mapped[str | None] = mapped_column(String(64), unique=True)  # their own page: prices, walkthrough booking, checklist
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class FamilyMessage(Base, UUIDPk, Timestamps, Tenant, Serializable):
    """A WhatsApp message to one family member, in their language, sent now or held until a sensible hour where they live."""

    __tablename__ = "family_messages"

    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("family_members.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="scheduled", server_default="scheduled", index=True)  # scheduled|sent|failed|cancelled
    body: Mapped[str] = mapped_column(Text, nullable=False)  # what goes out, in their language
    original: Mapped[str | None] = mapped_column(Text)  # what the rep typed, when it was translated
    language: Mapped[str] = mapped_column(String(8), default="en", server_default="en")
    template: Mapped[dict | None] = mapped_column(JSONB)  # {"name", "language", "body", "param_names", "params"} outside the 24-hour window
    send_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    whatsapp_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("whatsapp_messages.id", ondelete="SET NULL"))
    error: Mapped[str | None] = mapped_column(String(400))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Walkthrough(Base, UUIDPk, Timestamps, Tenant, Serializable):
    """A video walkthrough a family member asked for (from their page, or a rep on their behalf). The rep confirms it with a
    meeting link, which puts it on the calendar and tells the member the time where they live."""

    __tablename__ = "walkthroughs"

    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("family_members.id", ondelete="CASCADE"), index=True)
    starts_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    timezone: Mapped[str] = mapped_column(String(64))  # the member's, when they asked
    status: Mapped[str] = mapped_column(String(12), default="requested", server_default="requested", index=True)  # requested|confirmed|cancelled
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("units.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(String(500))
    requested_via: Mapped[str] = mapped_column(String(10), default="link", server_default="link")  # link|rep
    meeting_url: Mapped[str | None] = mapped_column(String(500))
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
