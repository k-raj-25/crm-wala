from __future__ import annotations

import uuid

from flask import Blueprint, g, request
from pydantic import Field

from app.core.auth import protect
from app.core.errors import ApiError, not_found
from app.core.responses import created, no_content, ok
from app.extensions import db
from app.models import Automation, AutomationRun
from app.models.base import utcnow
from app.schemas.common import Schema, parse, provided
from app.services import analytics, audit, automation as engine
from app.services.usage import check_limit

bp = Blueprint("automations", __name__, url_prefix="/api/v1/automations")
FEATURE = "automation_builder"


class AutomationIn(Schema):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=400)
    trigger_type: str
    trigger_config: dict = Field(default_factory=dict)
    graph: dict
    is_active: bool = False


def _get(aid) -> Automation:
    a = db.session.query(Automation).filter_by(id=aid, workspace_id=g.workspace.id, deleted_at=None).one_or_none()
    if a is None:
        raise not_found("Automation")
    return a


@bp.get("/meta")
@protect("automations.read", feature=FEATURE)
def meta():
    return ok({"triggers": [{"key": k, **v} for k, v in engine.TRIGGERS.items()], "actions": [{"key": k, **v} for k, v in engine.ACTIONS.items()]})


@bp.get("")
@protect("automations.read", feature=FEATURE)
def list_():
    rows = db.session.query(Automation).filter_by(workspace_id=g.workspace.id, deleted_at=None).order_by(Automation.created_at.desc()).all()
    return ok([r.to_dict() for r in rows])


@bp.get("/<uuid:aid>")
@protect("automations.read", feature=FEATURE)
def get(aid):
    return ok(_get(aid).to_dict())


@bp.post("")
@protect("automations.create", feature=FEATURE)
def create():
    d = parse(AutomationIn)
    if d.trigger_type not in engine.TRIGGERS:
        raise ApiError(422, "validation_error", "Unknown trigger", {"trigger_type": "Unknown"})
    engine.validate_graph(d.graph, d.trigger_type)
    check_limit(g.workspace, "automations")
    a = Automation(workspace_id=g.workspace.id, created_by=g.user.id, **d.model_dump())
    db.session.add(a)
    db.session.flush()
    audit.record("automation.created", entity_type="automation", entity_id=a.id, summary=f"Created automation “{a.name}”")
    analytics.track("automation_created", {"trigger": a.trigger_type})
    db.session.commit()
    return created(a.to_dict())


@bp.patch("/<uuid:aid>")
@protect("automations.update", feature=FEATURE)
def update(aid):
    a = _get(aid)
    data = request.get_json(silent=True) or {}
    merged = {**{k: getattr(a, k) for k in ("name", "description", "trigger_type", "trigger_config", "graph", "is_active")}, **{k: v for k, v in data.items() if k in AutomationIn.model_fields}}
    d = parse(AutomationIn, merged)
    engine.validate_graph(d.graph, d.trigger_type)
    before = {"is_active": a.is_active, "name": a.name}
    for k, v in d.model_dump().items():
        setattr(a, k, v)
    audit.record("automation.updated", entity_type="automation", entity_id=a.id, summary=f"Updated automation “{a.name}”", before=before, after={"is_active": a.is_active, "name": a.name})
    db.session.commit()
    return ok(a.to_dict())


@bp.delete("/<uuid:aid>")
@protect("automations.delete", feature=FEATURE)
def delete(aid):
    a = _get(aid)
    a.deleted_at, a.is_active = utcnow(), False
    audit.record("automation.deleted", entity_type="automation", entity_id=a.id, summary=f"Deleted automation “{a.name}”")
    db.session.commit()
    return no_content()


@bp.get("/<uuid:aid>/runs")
@protect("automations.read", feature=FEATURE)
def runs(aid):
    _get(aid)
    rows = db.session.query(AutomationRun).filter_by(automation_id=aid, workspace_id=g.workspace.id).order_by(AutomationRun.created_at.desc()).limit(50).all()
    return ok([r.to_dict() for r in rows])


@bp.post("/<uuid:aid>/test")
@protect("automations.update", feature=FEATURE)
def test_run(aid):
    """Dry run: walks the workflow and reports what would happen without side effects."""
    a = _get(aid)
    run = AutomationRun(workspace_id=g.workspace.id, automation_id=a.id, trigger_payload=request.get_json(silent=True) or {}, steps=[])
    engine.execute(run, a, dry_run=True)
    return ok({"status": run.status, "steps": run.steps})
