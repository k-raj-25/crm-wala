from __future__ import annotations

import datetime as dt
import decimal
import uuid

from flask import Blueprint, g, request
from sqlalchemy import func

from app.core import search_expr
from app.core.auth import protect, require
from app.core.crud import CrudResource, users_map
from app.core.errors import ApiError, bad_request
from app.core.responses import ok
from app.extensions import db
from app.models import Company, Contact, Deal, Lead, Pipeline, PipelineStage, Project, Unit
from app.models.base import utcnow
from app.schemas.common import Schema, parse
from app.schemas.crm import DealIn, DealPatch
from app.services import activities, analytics, audit, events, inventory, notifications, scoring
from app.services.tags import ensure_tags

bp = Blueprint("deals", __name__, url_prefix="/api/v1/deals")


def default_pipeline() -> Pipeline:
    p = db.session.query(Pipeline).filter_by(workspace_id=g.workspace.id, is_default=True, deleted_at=None).first()
    if p is None:
        p = db.session.query(Pipeline).filter_by(workspace_id=g.workspace.id, deleted_at=None).order_by(Pipeline.position).first()
    if p is None:
        raise ApiError(409, "no_pipeline", "Create a pipeline first")
    return p


def _stage(stage_id, pipeline_id=None) -> PipelineStage:
    q = db.session.query(PipelineStage).filter(PipelineStage.id == stage_id, PipelineStage.workspace_id == g.workspace.id)
    if pipeline_id:
        q = q.filter(PipelineStage.pipeline_id == pipeline_id)
    s = q.one_or_none()
    if s is None:
        raise ApiError(422, "validation_error", "Stage not found in that pipeline", {"stage_id": "Not found"})
    return s


def _next_position(stage_id) -> float:
    m = db.session.query(func.max(Deal.position)).filter(Deal.stage_id == stage_id, Deal.workspace_id == g.workspace.id).scalar()
    return float(m or 0) + 1000.0


def apply_stage(deal: Deal, stage: PipelineStage) -> None:
    deal.stage_id, deal.pipeline_id = stage.id, stage.pipeline_id
    deal.stage = stage
    deal.stage_entered_at = utcnow()
    deal.probability = stage.probability
    if stage.kind == "won":
        deal.status, deal.closed_at, deal.probability = "won", utcnow(), 100
    elif stage.kind == "lost":
        deal.status, deal.closed_at, deal.probability = "lost", utcnow(), 0
    else:
        deal.status, deal.closed_at, deal.lost_reason = "open", None, None


def create_deal_record(**kw) -> Deal:
    pipeline = db.session.get(Pipeline, kw.pop("pipeline_id", None)) if kw.get("pipeline_id") else default_pipeline()
    stage = _stage(kw.pop("stage_id"), pipeline.id) if kw.get("stage_id") else db.session.query(PipelineStage).filter_by(
        pipeline_id=pipeline.id).order_by(PipelineStage.position).first()
    kw.pop("pipeline_id", None), kw.pop("stage_id", None)
    currency = kw.pop("currency", None) or pipeline.currency
    deal = Deal(workspace_id=g.workspace.id, pipeline_id=pipeline.id, stage_id=stage.id, currency=currency, **kw)
    deal.owner_id = deal.owner_id or g.user.id
    apply_stage(deal, stage)
    deal.position = _next_position(stage.id)
    db.session.add(deal)
    db.session.flush()
    activities.log_activity("created", f"Deal created in {stage.name}", deal_id=deal.id, contact_id=deal.contact_id, company_id=deal.company_id,
                            data={"value": float(deal.value)})
    events.emit("deal.created", {"deal_id": str(deal.id), "name": deal.name, "value": float(deal.value), "owner_id": str(deal.owner_id)})
    analytics.track("deal_created")
    return deal


class DealResource(CrudResource):
    name, entity_type, model = "deals", "deal", Deal
    create_schema, patch_schema = DealIn, DealPatch
    search_cols = [search_expr.DEALS]
    sort_fields = {
        "created_at": Deal.created_at, "updated_at": Deal.updated_at, "name": Deal.name, "value": Deal.value,
        "expected_close_date": Deal.expected_close_date, "probability": Deal.probability, "closed_at": Deal.closed_at,
        "last_activity_at": Deal.last_activity_at,
    }
    filters = {
        "status": ("in", Deal.status), "owner_id": ("in", Deal.owner_id), "company_id": ("in", Deal.company_id),
        "contact_id": ("in", Deal.contact_id), "pipeline_id": ("in", Deal.pipeline_id), "stage_id": ("in", Deal.stage_id),
        "priority": ("in", Deal.priority), "tags": ("array", Deal.tags), "value": ("num", Deal.value),
        "expected_close_date": ("date", Deal.expected_close_date), "created_at": ("date", Deal.created_at),
        "closed_at": ("date", Deal.closed_at), "source": ("in", Deal.source),
        "project_id": ("in", Deal.project_id), "unit_id": ("in", Deal.unit_id),
    }
    refs = {"owner_id": "member", "company_id": Company, "contact_id": Contact, "project_id": Project, "unit_id": Unit}
    custom_fields = True
    bulk_fields = {"priority"}
    export_columns = [
        ("Name", lambda o: o.name), ("Company", lambda o: o.company.name if o.company else ""),
        ("Contact", lambda o: o.contact.name if o.contact else ""), ("Value", lambda o: o.value), ("Currency", lambda o: o.currency),
        ("Stage", lambda o: o.stage.name), ("Status", lambda o: o.status), ("Probability", lambda o: o.probability),
        ("Priority", lambda o: o.priority), ("Expected close", lambda o: o.expected_close_date), ("Owner", lambda o: o._owner_name),
        ("Source", lambda o: o.source), ("Tags", lambda o: o.tags), ("Created", lambda o: o.created_at.isoformat()),
    ]

    def extra_filters(self, q):
        if request.args.get("closing") == "this_month":
            today = utcnow().date()
            start = today.replace(day=1)
            end = (start + dt.timedelta(days=32)).replace(day=1)
            q = q.where(Deal.status == "open", Deal.expected_close_date >= start, Deal.expected_close_date < end)
        if request.args.get("stale_days", "").isdigit():
            q = q.where(Deal.status == "open", Deal.last_activity_at < utcnow() - dt.timedelta(days=int(request.args["stale_days"])))
        return q

    def serialize_many(self, objs):
        out = super().serialize_many(objs)
        units, projects = inventory.labels_for({o.unit_id for o in objs}, {o.project_id for o in objs})
        for d, o in zip(out, objs):
            d["unit"] = {"id": str(o.unit_id), "label": units.get(o.unit_id)} if o.unit_id else None
            d["project"] = {"id": str(o.project_id), "name": projects.get(o.project_id)} if o.project_id else None
            d["company"] = {"id": str(o.company.id), "name": o.company.name} if o.company else None
            d["contact"] = {"id": str(o.contact.id), "name": o.contact.name} if o.contact else None
            d["stage"] = {"id": str(o.stage.id), "name": o.stage.name, "kind": o.stage.kind, "color": o.stage.color, "position": o.stage.position}
            d["weighted_value"] = round(float(o.value) * o.probability / 100, 2)
            d["days_in_stage"] = (utcnow() - o.stage_entered_at).days if o.stage_entered_at else None
        return out

    def create(self):
        data = parse(DealIn)
        d = data.model_dump()
        self.validate_refs(d)
        from app.services import custom_fields as cf

        custom = cf.validate(g.workspace.id, "deal", d.pop("custom"))
        prob = d.pop("probability", None)
        inventory.link_project(d)
        deal = create_deal_record(custom=custom, **{k: v for k, v in d.items()})
        if prob is not None:
            deal.probability = prob
        ensure_tags(deal.tags)
        audit.record("deal.created", entity_type="deal", entity_id=deal.id, summary=f"Created deal “{deal.name}”", after=deal.to_dict())
        db.session.commit()
        from app.core.responses import created

        return created(self.serialize(deal))

    def prepare_update(self, deal, changes):
        if "unit_id" in changes:
            inventory.link_project(changes)
        stage_id, pipeline_id = changes.pop("stage_id", None), changes.pop("pipeline_id", None)
        if stage_id or pipeline_id:
            pid = pipeline_id or deal.pipeline_id
            stage = _stage(stage_id, pid) if stage_id else db.session.query(PipelineStage).filter_by(pipeline_id=pid).order_by(PipelineStage.position).first()
            if stage is None:
                raise ApiError(422, "validation_error", "Pipeline not found", {"pipeline_id": "Not found"})
            changes["_stage"] = stage
        return changes

    def after_update(self, deal, before, changes):
        stage = changes.pop("_stage", None)
        if "tags" in changes:
            ensure_tags(deal.tags)
        if stage is not None and stage.id != deal.stage_id:
            self._move(deal, stage, before)

    def _move(self, deal: Deal, stage: PipelineStage, before: dict, position: float | None = None) -> None:
        old_stage = db.session.get(PipelineStage, before["stage_id"]) if isinstance(before["stage_id"], (str, uuid.UUID)) else deal.stage
        apply_stage(deal, stage)
        deal.position = position if position is not None else _next_position(stage.id)
        inventory.sync_deal_to_unit(deal, stage.kind)
        kind = {"won": "won", "lost": "lost"}.get(stage.kind, "stage_changed")
        title = {"won": "Deal won 🎉", "lost": "Deal lost"}.get(stage.kind, f"Moved from {old_stage.name if old_stage else '—'} to {stage.name}")
        activities.log_activity(kind, title, deal_id=deal.id, contact_id=deal.contact_id, company_id=deal.company_id,
                                data={"from": old_stage.name if old_stage else None, "to": stage.name, "value": float(deal.value)})
        events.emit("deal.stage_changed", {"deal_id": str(deal.id), "name": deal.name, "stage": stage.name, "stage_kind": stage.kind, "value": float(deal.value)})
        if stage.kind in ("won", "lost"):
            targets = {deal.owner_id, *notifications.workspace_admins(g.workspace.id)}
            notifications.notify(g.workspace.id, targets, "deal_update", f"Deal {stage.kind}: {deal.name}", f"{g.user.name} marked this deal as {stage.kind}.",
                                 f"/app/deals/{deal.id}", exclude_user_id=g.user.id)
            analytics.track(f"deal_{stage.kind}", {"value": float(deal.value)})
        elif deal.owner_id and deal.owner_id != g.user.id:
            notifications.notify(g.workspace.id, [deal.owner_id], "deal_update", f"{deal.name} moved to {stage.name}", None, f"/app/deals/{deal.id}", exclude_user_id=g.user.id)


res = DealResource()
res.register(bp)


class MoveIn(Schema):
    stage_id: uuid.UUID
    position: float | None = None
    lost_reason: str | None = None


@bp.post("/<uuid:ident>/move")
@protect("deals.update")
def move(ident):
    deal = res.get_or_404(ident)
    data = parse(MoveIn)
    stage = _stage(data.stage_id)
    if stage.kind in ("won", "lost"):
        require("deals.close")
    before = deal.to_dict()
    if stage.id == deal.stage_id:
        if data.position is not None:
            deal.position = data.position
    else:
        res._move(deal, stage, before, data.position)
        if stage.kind == "lost" and data.lost_reason:
            deal.lost_reason = data.lost_reason
    b, a = audit.diff(before, deal.to_dict(), ignore=("updated_at", "position"))
    if a:
        audit.record("deal.stage_changed", entity_type="deal", entity_id=deal.id, summary=f"Moved deal “{deal.name}” to {stage.name}", before=b, after=a)
    db.session.commit()
    return ok(res.serialize(deal))


@bp.get("/<uuid:ident>/ai/probability")
@protect("deals.read")
def probability_suggestion(ident):
    deal = res.get_or_404(ident)
    p, notes = scoring.deal_probability(deal)
    return ok({"suggested": p, "current": deal.probability, "reasons": notes})
