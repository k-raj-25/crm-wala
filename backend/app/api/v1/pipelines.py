from __future__ import annotations

import uuid

from flask import Blueprint, g, request
from pydantic import Field
from sqlalchemy import func

from app.core.auth import protect
from app.core.crud import users_map
from app.core.errors import ApiError, conflict, not_found
from app.core.responses import created, no_content, ok
from app.extensions import db
from app.models import Deal, Pipeline, PipelineStage
from app.models.base import utcnow
from app.schemas.common import Schema, parse, patchify, provided
from app.services import audit
from app.services.usage import check_limit

bp = Blueprint("pipelines", __name__, url_prefix="/api/v1/pipelines")


class PipelineIn(Schema):
    name: str = Field(min_length=1, max_length=80)
    is_default: bool = False
    currency: str = Field(default="INR", min_length=3, max_length=3)


class StageIn(Schema):
    name: str = Field(min_length=1, max_length=60)
    probability: int = Field(default=0, ge=0, le=100)
    kind: str = Field(default="open", pattern="^(open|won|lost)$")
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


StagePatch = patchify(StageIn, "StagePatch")
PipelinePatch = patchify(PipelineIn, "PipelinePatch")


def _ser(p: Pipeline) -> dict:
    return {**p.to_dict(), "stages": [s.to_dict() for s in p.stages]}


def _get(pid) -> Pipeline:
    p = db.session.query(Pipeline).filter_by(id=pid, workspace_id=g.workspace.id, deleted_at=None).one_or_none()
    if p is None:
        raise not_found("Pipeline")
    return p


@bp.get("")
@protect("pipelines.read")
def list_pipelines():
    rows = db.session.query(Pipeline).filter_by(workspace_id=g.workspace.id, deleted_at=None).order_by(Pipeline.position, Pipeline.created_at).all()
    return ok([_ser(p) for p in rows])


@bp.post("")
@protect("pipelines.create")
def create_pipeline():
    data = parse(PipelineIn)
    check_limit(g.workspace, "pipelines")
    from app.services.workspaces import DEFAULT_STAGES

    n = db.session.query(func.count(Pipeline.id)).filter_by(workspace_id=g.workspace.id, deleted_at=None).scalar()
    p = Pipeline(workspace_id=g.workspace.id, name=data.name, currency=data.currency, position=n, is_default=False)
    db.session.add(p)
    db.session.flush()
    for i, (name, prob, kind, color) in enumerate(DEFAULT_STAGES):
        db.session.add(PipelineStage(workspace_id=g.workspace.id, pipeline_id=p.id, name=name, position=i, probability=prob, kind=kind, color=color))
    db.session.flush()
    if data.is_default:
        _make_default(p)
    audit.record("pipeline.created", entity_type="pipeline", entity_id=p.id, summary=f"Created pipeline “{p.name}”")
    db.session.commit()
    db.session.refresh(p)
    return created(_ser(p))


def _make_default(p: Pipeline) -> None:
    db.session.query(Pipeline).filter(Pipeline.workspace_id == g.workspace.id, Pipeline.id != p.id).update({"is_default": False})
    p.is_default = True


@bp.patch("/<uuid:pid>")
@protect("pipelines.update")
def update_pipeline(pid):
    p = _get(pid)
    ch = provided(parse(PipelinePatch))
    if "name" in ch and ch["name"]:
        p.name = ch["name"]
    if ch.get("is_default"):
        _make_default(p)
    audit.record("pipeline.updated", entity_type="pipeline", entity_id=p.id, summary=f"Updated pipeline “{p.name}”", after=ch)
    db.session.commit()
    return ok(_ser(p))


@bp.delete("/<uuid:pid>")
@protect("pipelines.delete")
def delete_pipeline(pid):
    p = _get(pid)
    if p.is_default:
        raise conflict("The default pipeline can't be deleted. Make another pipeline the default first.", "default_pipeline")
    open_deals = db.session.query(func.count(Deal.id)).filter(Deal.pipeline_id == p.id, Deal.deleted_at.is_(None), Deal.status == "open").scalar()
    if open_deals:
        raise conflict(f"This pipeline still has {open_deals} open deal(s). Move or close them first.", "pipeline_has_deals")
    p.deleted_at = utcnow()
    audit.record("pipeline.deleted", entity_type="pipeline", entity_id=p.id, summary=f"Deleted pipeline “{p.name}”")
    db.session.commit()
    return no_content()


# ---- stages -----------------------------------------------------------------------------

def _check_closing_stages(pipeline_id, excluding=None) -> None:
    q = db.session.query(PipelineStage.kind).filter(PipelineStage.pipeline_id == pipeline_id)
    if excluding:
        q = q.filter(PipelineStage.id != excluding)
    kinds = {k for (k,) in q.all()}
    if "won" not in kinds or "lost" not in kinds:
        raise conflict("A pipeline needs at least one Won stage and one Lost stage.", "closing_stages_required")


@bp.post("/<uuid:pid>/stages")
@protect("pipelines.update")
def add_stage(pid):
    p = _get(pid)
    data = parse(StageIn)
    # New open stages go before the first closing stage.
    stages = p.stages
    pos = next((s.position for s in stages if s.kind != "open"), len(stages)) if data.kind == "open" else len(stages)
    for s in stages:
        if s.position >= pos:
            s.position += 1
    st = PipelineStage(workspace_id=g.workspace.id, pipeline_id=p.id, position=pos, **data.model_dump())
    db.session.add(st)
    audit.record("pipeline.stage_added", entity_type="pipeline", entity_id=p.id, summary=f"Added stage “{st.name}” to {p.name}")
    db.session.commit()
    db.session.refresh(p)
    return created(_ser(p))


@bp.patch("/<uuid:pid>/stages/<uuid:sid>")
@protect("pipelines.update")
def update_stage(pid, sid):
    p = _get(pid)
    st = db.session.query(PipelineStage).filter_by(id=sid, pipeline_id=p.id).one_or_none()
    if st is None:
        raise not_found("Stage")
    ch = provided(parse(StagePatch))
    if "kind" in ch and ch["kind"] != st.kind:
        st.kind = ch["kind"]
        db.session.flush()
        _check_closing_stages(p.id)
    for k in ("name", "probability", "color"):
        if k in ch and ch[k] is not None:
            setattr(st, k, ch[k])
    audit.record("pipeline.stage_updated", entity_type="pipeline", entity_id=p.id, summary=f"Updated stage “{st.name}”", after=ch)
    db.session.commit()
    db.session.refresh(p)
    return ok(_ser(p))


@bp.delete("/<uuid:pid>/stages/<uuid:sid>")
@protect("pipelines.update")
def delete_stage(pid, sid):
    p = _get(pid)
    st = db.session.query(PipelineStage).filter_by(id=sid, pipeline_id=p.id).one_or_none()
    if st is None:
        raise not_found("Stage")
    _check_closing_stages(p.id, excluding=st.id)
    count = db.session.query(func.count(Deal.id)).filter(Deal.stage_id == st.id).scalar()
    if count:
        target_id = request.args.get("move_to")
        if not target_id:
            raise conflict(f"{count} deal(s) are in this stage. Choose a stage to move them to.", "stage_has_deals", {"count": count})
        target = db.session.query(PipelineStage).filter_by(id=target_id, pipeline_id=p.id).one_or_none()
        if target is None or target.id == st.id:
            raise ApiError(422, "validation_error", "Invalid target stage", {"move_to": "Invalid"})
        for d in db.session.query(Deal).filter(Deal.stage_id == st.id).all():
            d.stage_id, d.probability = target.id, target.probability
            if target.kind != "open":
                d.status = target.kind
                d.closed_at = d.closed_at or utcnow()
            else:
                d.status, d.closed_at = "open", None
    db.session.delete(st)
    db.session.flush()
    for i, s in enumerate(db.session.query(PipelineStage).filter_by(pipeline_id=p.id).order_by(PipelineStage.position).all()):
        s.position = i
    audit.record("pipeline.stage_deleted", entity_type="pipeline", entity_id=p.id, summary=f"Deleted stage “{st.name}”")
    db.session.commit()
    db.session.refresh(p)
    return ok(_ser(p))


class OrderIn(Schema):
    ids: list[uuid.UUID]


@bp.put("/<uuid:pid>/stages/order")
@protect("pipelines.update")
def reorder_stages(pid):
    p = _get(pid)
    ids = parse(OrderIn).ids
    current = {s.id: s for s in p.stages}
    if set(ids) != set(current):
        raise ApiError(422, "validation_error", "Provide every stage exactly once", {"ids": "Mismatch"})
    for i, sid in enumerate(ids):
        current[sid].position = i
    db.session.commit()
    db.session.refresh(p)
    return ok(_ser(p))


# ---- Kanban board -----------------------------------------------------------------------

@bp.get("/<uuid:pid>/board")
@protect("deals.read")
def board(pid):
    from app.api.v1.deals import res as deal_res

    p = _get(pid)
    per_stage = min(int(request.args.get("per_stage", 40)), 100)
    stages = p.stages
    base = deal_res.apply_filters(deal_res.apply_search(deal_res.base_query().where(Deal.pipeline_id == p.id)))
    sub = base.subquery()
    agg = db.session.query(sub.c.stage_id, func.count(), func.coalesce(func.sum(sub.c.value), 0), func.coalesce(func.sum(sub.c.value * sub.c.probability / 100), 0)).group_by(sub.c.stage_id).all()
    totals = {r[0]: (r[1], float(r[2]), float(r[3])) for r in agg}
    columns = []
    for s in stages:
        rows = db.session.scalars(base.where(Deal.stage_id == s.id).order_by(Deal.position.asc(), Deal.created_at.desc()).limit(per_stage)).unique().all()
        count, total, weighted = totals.get(s.id, (0, 0.0, 0.0))
        columns.append({"stage": s.to_dict(), "count": count, "total_value": total, "weighted_value": weighted,
                        "deals": deal_res.serialize_many(list(rows)), "has_more": count > len(rows)})
    return ok({"pipeline": {**p.to_dict()}, "columns": columns})
