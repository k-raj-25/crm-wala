from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from app.core.errors import payment_required
from app.extensions import db
from app.models import (
    AiUsage, Automation, Contact, Email, FileAsset, Invitation, Pipeline, Workspace, WorkspaceMember,
)
from app.models.base import utcnow
from app.services.features import plan_limits

LABELS = {
    "users": "team members", "contacts": "contacts", "pipelines": "pipelines", "automations": "automations",
    "ai_actions_month": "AI actions this month", "storage_mb": "MB of storage", "emails_month": "emails this month",
}


def _month_start() -> dt.datetime:
    n = utcnow()
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def current_usage(ws: Workspace) -> dict[str, int]:
    s = db.session
    wid = ws.id
    users = s.scalar(select(func.count()).select_from(WorkspaceMember).where(
        WorkspaceMember.workspace_id == wid, WorkspaceMember.status == "active")) or 0
    pending = s.scalar(select(func.count()).select_from(Invitation).where(
        Invitation.workspace_id == wid, Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None),
        Invitation.expires_at > utcnow())) or 0
    return {
        "users": users + pending,
        "contacts": s.scalar(select(func.count()).select_from(Contact).where(Contact.workspace_id == wid, Contact.deleted_at.is_(None))) or 0,
        "pipelines": s.scalar(select(func.count()).select_from(Pipeline).where(Pipeline.workspace_id == wid, Pipeline.deleted_at.is_(None))) or 0,
        "automations": s.scalar(select(func.count()).select_from(Automation).where(Automation.workspace_id == wid, Automation.deleted_at.is_(None))) or 0,
        "ai_actions_month": s.scalar(select(func.count()).select_from(AiUsage).where(AiUsage.workspace_id == wid, AiUsage.created_at >= _month_start())) or 0,
        "storage_mb": int((s.scalar(select(func.coalesce(func.sum(FileAsset.size_bytes), 0)).where(
            FileAsset.workspace_id == wid, FileAsset.deleted_at.is_(None))) or 0) / (1024 * 1024)),
        "emails_month": s.scalar(select(func.count()).select_from(Email).where(
            Email.workspace_id == wid, Email.direction == "outbound", Email.created_at >= _month_start())) or 0,
    }


def check_limit(ws: Workspace, key: str, adding: int = 1) -> None:
    limit = plan_limits(ws).get(key)
    if limit is None:
        return
    used = current_usage(ws).get(key, 0)
    if used + adding > limit:
        raise payment_required(
            f"Your plan includes up to {limit:,} {LABELS.get(key, key)}. Upgrade to add more.",
            code="plan_limit_reached", details={"limit": key, "max": limit, "used": used},
        )
