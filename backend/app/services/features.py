from __future__ import annotations

import hashlib

from app.core.features import FEATURES
from app.extensions import db
from app.models import FeatureFlag, Plan, Workspace


def get_plan(key: str) -> Plan | None:
    return db.session.query(Plan).filter_by(key=key).one_or_none()


def _flag_on(flag: FeatureFlag | None, workspace_id: str) -> bool:
    if flag is None:
        return True
    override = (flag.workspace_overrides or {}).get(workspace_id)
    if override is not None:
        return bool(override)
    if not flag.enabled:
        return False
    if flag.rollout_percent >= 100:
        return True
    bucket = int(hashlib.sha256(f"{flag.key}:{workspace_id}".encode()).hexdigest(), 16) % 100
    return bucket < flag.rollout_percent


def workspace_features(ws: Workspace) -> set[str]:
    """Effective features = plan entitlement AND Super Admin feature flag."""
    plan = get_plan(ws.plan_key)
    entitled = set(plan.features) if plan else set()
    flags = {f.key: f for f in db.session.query(FeatureFlag).all()}
    return {f for f in FEATURES if f in entitled and _flag_on(flags.get(f), str(ws.id))}


def plan_limits(ws: Workspace) -> dict:
    plan = get_plan(ws.plan_key)
    limits = dict(plan.limits) if plan else {}
    limits.update(ws.limit_overrides or {})
    return limits
