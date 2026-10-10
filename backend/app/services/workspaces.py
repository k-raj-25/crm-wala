from __future__ import annotations

import datetime as dt
import re
import secrets
import uuid

from sqlalchemy import select

from app.core.features import DEFAULT_FLAGS, DEFAULT_PLANS, DEFAULT_PLATFORM_SETTINGS
from app.core.permissions import ALL, PERMISSIONS, SYSTEM_ROLES
from app.extensions import db
from app.models import (
    FeatureFlag, Permission, Pipeline, PipelineStage, Plan, PlatformEmailTemplate, PlatformSetting, Role, User,
    Workspace, WorkspaceMember,
)
from app.models.base import utcnow
from app.services import analytics
from app.services import settings as platform_settings
from app.services.email_templates import DEFAULT_TEMPLATES

# Keys stay stable (reports and follow-up filters rely on them); labels speak the realtor's language.
DEFAULT_LEAD_STATUSES = [
    {"key": "new", "label": "New enquiry", "color": "#6366f1"},
    {"key": "contacted", "label": "Contacted", "color": "#0ea5e9"},
    {"key": "qualified", "label": "Interested", "color": "#10b981"},
    {"key": "unqualified", "label": "Not interested", "color": "#94a3b8"},
    {"key": "converted", "label": "Became a client", "color": "#8b5cf6"},
    {"key": "lost", "label": "Lost", "color": "#ef4444"},
]

DEFAULT_STAGES = [
    ("Enquiry", 10, "open", "#94a3b8"), ("Site Visit", 30, "open", "#6366f1"), ("Shortlisted", 50, "open", "#0ea5e9"),
    ("Negotiation", 70, "open", "#f59e0b"), ("Token Paid", 90, "open", "#f97316"), ("Closed", 100, "won", "#10b981"),
    ("Lost", 0, "lost", "#ef4444"),
]


def seed_platform() -> None:
    """Idempotently create plans, roles, permissions, flags, settings and email templates. Safe to run on every deploy."""
    s = db.session
    for key, (group, desc) in PERMISSIONS.items():
        if s.get(Permission, key) is None:
            s.add(Permission(key=key, group=group, description=desc))
    for key, spec in SYSTEM_ROLES.items():
        role = s.query(Role).filter(Role.key == key, Role.workspace_id.is_(None)).one_or_none()
        if role is None:
            s.add(Role(key=key, name=spec["name"], description=spec["description"], permissions=spec["permissions"],
                       is_system=True, rank=spec["rank"]))
        else:  # keep system roles in sync with code defaults
            role.permissions, role.rank, role.name = spec["permissions"], spec["rank"], spec["name"]
    for p in DEFAULT_PLANS:
        if s.query(Plan).filter_by(key=p["key"]).one_or_none() is None:
            s.add(Plan(**p))
    for key, name, desc in DEFAULT_FLAGS:
        if s.get(FeatureFlag, key) is None:
            s.add(FeatureFlag(key=key, name=name, description=desc))
    for key, (value, desc) in DEFAULT_PLATFORM_SETTINGS.items():
        if s.get(PlatformSetting, key) is None:
            s.add(PlatformSetting(key=key, value=value, description=desc))
    for key, t in DEFAULT_TEMPLATES.items():
        if s.get(PlatformEmailTemplate, key) is None:
            s.add(PlatformEmailTemplate(key=key, name=t["name"], subject=t["subject"], body_html=t["body"], variables=t["variables"]))
    s.commit()


def system_role(key: str) -> Role:
    r = db.session.query(Role).filter(Role.key == key, Role.workspace_id.is_(None)).one_or_none()
    if r is None:
        seed_platform()
        r = db.session.query(Role).filter(Role.key == key, Role.workspace_id.is_(None)).one()
    return r


def unique_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "workspace"
    slug = base
    while db.session.scalar(select(Workspace.id).where(Workspace.slug == slug)):
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


def create_default_pipeline(ws: Workspace, name: str = "Property Deals", default: bool = True) -> Pipeline:
    p = Pipeline(workspace_id=ws.id, name=name, is_default=default, currency=ws.currency)
    db.session.add(p)
    db.session.flush()
    for i, (n, prob, kind, color) in enumerate(DEFAULT_STAGES):
        db.session.add(PipelineStage(workspace_id=ws.id, pipeline_id=p.id, name=n, position=i, probability=prob, kind=kind, color=color))
    db.session.flush()
    return p


def create_workspace(owner: User, name: str, *, company_size: str | None = None, industry: str | None = None,
                     is_demo: bool = False, start_trial: bool = True) -> Workspace:
    from app.core.tenant import tenant_scope

    now = utcnow()
    ws = Workspace(
        id=uuid.uuid4(), name=name, slug=unique_slug(name), owner_id=owner.id, company_size=company_size, industry=industry,
        is_demo=is_demo, plan_key="trial", subscription_status="trialing",
        settings={"lead_statuses": DEFAULT_LEAD_STATUSES, "public_form_token": secrets.token_urlsafe(18)},
    )
    if start_trial:
        ws.trial_started_at = now
        ws.trial_ends_at = now + dt.timedelta(days=platform_settings.trial_days())
    db.session.add(ws)
    db.session.flush()
    db.session.add(WorkspaceMember(workspace_id=ws.id, user_id=owner.id, role_id=system_role("owner").id))
    with tenant_scope(ws.id):
        create_default_pipeline(ws)
    analytics.track("workspace_created", {"industry": industry, "size": company_size}, workspace_id=ws.id, user_id=owner.id)
    return ws
