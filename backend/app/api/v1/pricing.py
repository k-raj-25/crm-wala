"""Airline-style pricing for flats: demand on the tower, price suggestions the owner applies or dismisses, and what happened after."""
from __future__ import annotations

import decimal
import uuid
from typing import Literal

from flask import Blueprint, g, request
from pydantic import Field

from app.core.auth import protect
from app.core.permissions import has_permission
from app.core.errors import not_found
from app.core.responses import ok
from app.extensions import db
from app.models import PriceChange, Project
from app.schemas.common import Schema, parse
from app.services import pricing as svc

bp = Blueprint("pricing", __name__, url_prefix="/api/v1/pricing")


class ActIn(Schema):
    segment_key: str = Field(min_length=3, max_length=200)
    rule: Literal["raise_hot", "cut_cold"]
    headline: str | None = Field(default=None, max_length=400)


class ApplyIn(ActIn):
    pct: decimal.Decimal = Field(ge=-svc.MAX_PCT, le=svc.MAX_PCT, decimal_places=2)


def _project(pid) -> Project:
    p = db.session.query(Project).filter(Project.id == pid, Project.workspace_id == g.workspace.id, Project.deleted_at.is_(None)).one_or_none()
    if p is None:
        raise not_found("Project")
    return p


@bp.get("/projects/<uuid:pid>/demand")
@protect("pricing.read")
def demand(pid):
    """Demand level per flat (hot, warm, cool, cold) for colouring the tower."""
    p = _project(pid)
    tid = request.args.get("tower_id")
    try:
        tid = uuid.UUID(tid) if tid else None
    except ValueError:
        raise not_found("Tower")
    return ok({"window_days": svc.WINDOW_DAYS, "units": svc.unit_levels(p.id, tid)})


@bp.get("/projects/<uuid:pid>/suggestions")
@protect("pricing.read")
def suggestions(pid):
    p = _project(pid)
    return ok({"window_days": svc.WINDOW_DAYS, "cooldown_days": svc.COOLDOWN_DAYS, "can_apply": has_permission(g.permissions, "pricing.apply"), "suggestions": svc.suggestions(p.id)})


@bp.post("/projects/<uuid:pid>/apply")
@protect("pricing.apply")
def apply(pid):
    p = _project(pid)
    d = parse(ApplyIn)
    pc = svc.apply(p, d.segment_key, d.rule, d.pct, d.headline)
    db.session.commit()
    return ok({**pc.to_dict(), "pct": float(pc.pct)})


@bp.post("/projects/<uuid:pid>/dismiss")
@protect("pricing.apply")
def dismiss(pid):
    p = _project(pid)
    d = parse(ActIn)
    pc = svc.dismiss(p, d.segment_key, d.rule, d.headline)
    db.session.commit()
    return ok({**pc.to_dict(), "pct": float(pc.pct)})


@bp.get("/projects/<uuid:pid>/changes")
@protect("pricing.read")
def changes(pid):
    p = _project(pid)
    return ok(svc.changes(p.id))


@bp.post("/changes/<uuid:cid>/undo")
@protect("pricing.apply")
def undo(cid):
    pc = db.session.query(PriceChange).filter(PriceChange.id == cid, PriceChange.workspace_id == g.workspace.id).one_or_none()
    if pc is None:
        raise not_found("Price change")
    out = svc.undo(pc)
    db.session.commit()
    return ok(out)
