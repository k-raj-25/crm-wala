"""Workspace access state machine: trial -> active -> past_due(grace) -> restricted.

Customer data is NEVER deleted when access is restricted; restricted workspaces can still log in,
view billing, upgrade and export their data.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.models import Workspace
from app.models.base import utcnow


@dataclass
class Access:
    state: str  # full | grace | restricted | suspended
    reason: str | None = None  # trial_expired | payment_failed | subscription_ended | suspended
    seconds_left: int | None = None  # trial or grace remaining
    trial_stage: str | None = None  # day1 | day2 | final | expired
    ends_at: dt.datetime | None = None

    @property
    def allowed(self) -> bool:
        return self.state in ("full", "grace")

    def to_dict(self) -> dict:
        return {
            "state": self.state, "reason": self.reason, "seconds_left": self.seconds_left,
            "trial_stage": self.trial_stage, "ends_at": self.ends_at.isoformat() if self.ends_at else None,
        }


def trial_stage(ws: Workspace, now: dt.datetime) -> str | None:
    if not ws.trial_started_at or not ws.trial_ends_at:
        return None
    if now >= ws.trial_ends_at:
        return "expired"
    remaining = ws.trial_ends_at - now
    if remaining <= dt.timedelta(hours=24):
        return "final"
    if now - ws.trial_started_at < dt.timedelta(hours=24):
        return "day1"
    return "day2"


def compute_access(ws: Workspace, now: dt.datetime | None = None) -> Access:
    now = now or utcnow()
    if ws.status == "suspended":
        return Access("suspended", "suspended")
    s = ws.subscription_status
    if s == "trialing":
        if ws.trial_ends_at and now < ws.trial_ends_at:
            return Access("full", None, int((ws.trial_ends_at - now).total_seconds()), trial_stage(ws, now), ws.trial_ends_at)
        return Access("restricted", "trial_expired", 0, "expired", ws.trial_ends_at)
    if s == "active":
        return Access("full", ends_at=ws.current_period_end)
    if s == "past_due":
        if ws.grace_ends_at and now < ws.grace_ends_at:
            return Access("grace", "payment_failed", int((ws.grace_ends_at - now).total_seconds()), ends_at=ws.grace_ends_at)
        return Access("restricted", "payment_failed", 0)
    if s == "canceled":
        if ws.current_period_end and now < ws.current_period_end:
            return Access("full", "canceled", int((ws.current_period_end - now).total_seconds()), ends_at=ws.current_period_end)
        return Access("restricted", "subscription_ended", 0)
    return Access("restricted", "trial_expired" if s == "expired" else "subscription_ended", 0)
