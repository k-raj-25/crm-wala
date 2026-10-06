from __future__ import annotations

import datetime as dt
import decimal
import uuid

from flask import Blueprint, g, request
from sqlalchemy import func, or_

from app.core import search_expr
from app.core.auth import protect, require
from app.core.crud import CrudResource, ensure_ref, users_map
from app.core.errors import ApiError, conflict, bad_request
from app.core.responses import ok
from app.extensions import db
from app.models import Company, Contact, Deal, Lead, Pipeline, PipelineStage
from app.models.base import utcnow
from app.schemas.common import Schema, parse
from app.schemas.crm import LeadIn, LeadPatch
from app.services import activities, analytics, audit, events, notifications, scoring
from app.services.tags import ensure_tags
from app.services.usage import check_limit

bp = Blueprint("leads", __name__, url_prefix="/api/v1/leads")


def lead_statuses() -> list[str]:
    return [s["key"] for s in (g.workspace.settings or {}).get("lead_statuses", [])] or ["new"]


def rescore(lead: Lead) -> None:
    since = utcnow() - dt.timedelta(days=14)
    from app.models import Activity

    n = db.session.query(func.count(Activity.id)).filter(Activity.lead_id == lead.id, Activity.occurred_at >= since, Activity.type != "created").scalar() or 0
    lead.score, lead.score_reasons = scoring.score_lead(lead, n)


class LeadResource(CrudResource):
    name, entity_type, model = "leads", "lead", Lead
    create_schema, patch_schema = LeadIn, LeadPatch
    search_cols = [search_expr.LEADS]
    sort_fields = {
        "created_at": Lead.created_at, "updated_at": Lead.updated_at, "name": Lead.first_name, "status": Lead.status,
        "score": Lead.score, "company": Lead.company_name, "last_contacted_at": Lead.last_contacted_at,
        "next_follow_up_at": Lead.next_follow_up_at, "source": Lead.source,
    }
    filters = {
        "status": ("in", Lead.status), "source": ("in", Lead.source), "owner_id": ("in", Lead.owner_id), "tags": ("array", Lead.tags),
        "score": ("num", Lead.score), "created_at": ("date", Lead.created_at), "next_follow_up_at": ("date", Lead.next_follow_up_at),
        "last_contacted_at": ("date", Lead.last_contacted_at),
    }
    refs = {"owner_id": "member"}
    limit_key = None
    custom_fields = True
    bulk_fields = {"status", "source"}
    export_columns = [
        ("First name", lambda o: o.first_name), ("Last name", lambda o: o.last_name), ("Email", lambda o: o.email),
        ("Phone", lambda o: o.phone), ("Company", lambda o: o.company_name), ("Job title", lambda o: o.job_title),
        ("Source", lambda o: o.source), ("Status", lambda o: o.status), ("Owner", lambda o: o._owner_name), ("Score", lambda o: o.score),
        ("Tags", lambda o: o.tags), ("Location", lambda o: o.location), ("Created", lambda o: o.created_at.isoformat()),
        ("Last contacted", lambda o: o.last_contacted_at.isoformat() if o.last_contacted_at else ""),
        ("Next follow-up", lambda o: o.next_follow_up_at.isoformat() if o.next_follow_up_at else ""), ("Notes", lambda o: o.description),
    ]

    def label(self, o):
        return o.name

    def extra_filters(self, q):
        now = utcnow()
        f = request.args.get("follow_up")
        start, end = now.replace(hour=0, minute=0, second=0, microsecond=0), now.replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=1)
        open_ = Lead.status.in_(("new", "contacted", "qualified"))
        if f == "overdue":
            q = q.where(Lead.next_follow_up_at < start, open_)
        elif f == "today":
            q = q.where(Lead.next_follow_up_at >= start, Lead.next_follow_up_at < end)
        elif f == "upcoming":
            q = q.where(Lead.next_follow_up_at >= end)
        elif f == "none":
            q = q.where(Lead.next_follow_up_at.is_(None), open_)
        stale = request.args.get("stale_days")
        if stale and stale.isdigit():
            cutoff = now - dt.timedelta(days=int(stale))
            q = q.where(open_, or_(Lead.last_contacted_at.is_(None), Lead.last_contacted_at < cutoff))
        return q

    def _validate_status(self, status):
        if status not in lead_statuses():
            raise ApiError(422, "validation_error", "Unknown lead status", {"status": "Choose a valid status"})
        if status == "converted":
            raise ApiError(422, "validation_error", "Use “Convert lead” to convert a lead", {"status": "Use Convert lead"})

    def prepare_create(self, data):
        self._validate_status(data["status"])
        data["owner_id"] = data.get("owner_id") or g.user.id
        return data

    def after_create(self, lead, data):
        rescore(lead)
        ensure_tags(lead.tags)
        activities.log_activity("created", "Lead created", lead_id=lead.id, data={"source": lead.source})
        if lead.owner_id != g.user.id:
            notifications.notify(g.workspace.id, [lead.owner_id], "new_lead", f"New lead: {lead.name}",
                                 f"{g.user.name} assigned you a new lead.", f"/app/leads/{lead.id}", exclude_user_id=g.user.id)
        events.emit("lead.created", {"lead_id": str(lead.id), "owner_id": str(lead.owner_id), "email": lead.email, "name": lead.name})

    def prepare_update(self, lead, changes):
        if "status" in changes and changes["status"] != lead.status:
            if lead.status == "converted":
                raise ApiError(422, "validation_error", "Converted leads can't change status", {"status": "Already converted"})
            self._validate_status(changes["status"])
        return changes

    def after_update(self, lead, before, changes):
        if "tags" in changes:
            ensure_tags(lead.tags)
        if "status" in changes and before["status"] != lead.status:
            activities.log_activity("status_changed", f"Status changed from {before['status']} to {lead.status}", lead_id=lead.id,
                                    data={"from": before["status"], "to": lead.status})
        if "owner_id" in changes and before["owner_id"] != (str(lead.owner_id) if lead.owner_id else None):
            owner = users_map({lead.owner_id}).get(lead.owner_id)
            activities.log_activity("assigned", f"Assigned to {owner['name'] if owner else 'nobody'}", lead_id=lead.id)
            if lead.owner_id:
                notifications.notify(g.workspace.id, [lead.owner_id], "task_assigned", f"Lead assigned: {lead.name}",
                                     f"{g.user.name} assigned you this lead.", f"/app/leads/{lead.id}", exclude_user_id=g.user.id)
        rescore(lead)


res = LeadResource()
res.register(bp)


class ConvertIn(Schema):
    create_company: bool = True
    create_deal: bool = False
    deal_name: str | None = None
    deal_value: decimal.Decimal = decimal.Decimal(0)
    pipeline_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    expected_close_date: dt.date | None = None


@bp.post("/<uuid:ident>/convert")
@protect("leads.convert")
def convert(ident):
    lead = res.get_or_404(ident)
    if lead.converted_at:
        raise conflict("This lead has already been converted", "already_converted")
    data = parse(ConvertIn)
    require("contacts.create")
    check_limit(g.workspace, "contacts")
    company = None
    if lead.company_name and data.create_company:
        require("companies.create")
        company = db.session.query(Company).filter(Company.workspace_id == g.workspace.id, Company.deleted_at.is_(None),
                                                   func.lower(Company.name) == lead.company_name.lower()).first()
        if company is None:
            company = Company(workspace_id=g.workspace.id, name=lead.company_name, owner_id=lead.owner_id, location=lead.location)
            db.session.add(company)
            db.session.flush()
            activities.log_activity("created", "Company created from lead conversion", company_id=company.id)
    contact = Contact(workspace_id=g.workspace.id, first_name=lead.first_name, last_name=lead.last_name, email=lead.email, phone=lead.phone,
                      job_title=lead.job_title, company_id=company.id if company else None, owner_id=lead.owner_id, location=lead.location,
                      tags=list(lead.tags or []), description=lead.description, custom=dict(lead.custom or {}), source_lead_id=lead.id,
                      last_contacted_at=lead.last_contacted_at)
    db.session.add(contact)
    db.session.flush()
    deal = None
    if data.create_deal:
        require("deals.create")
        from app.api.v1.deals import create_deal_record

        deal = create_deal_record(name=data.deal_name or f"{lead.company_name or lead.name} — New deal", value=data.deal_value,
                                  company_id=company.id if company else None, contact_id=contact.id, pipeline_id=data.pipeline_id,
                                  stage_id=data.stage_id, owner_id=lead.owner_id, source=lead.source, lead_id=lead.id,
                                  expected_close_date=data.expected_close_date, lead_score=lead.score)
    lead.status, lead.converted_at = "converted", utcnow()
    lead.converted_contact_id, lead.converted_deal_id = contact.id, deal.id if deal else None
    rescore(lead)
    # Carry the lead's history over to the new contact.
    from app.models import Activity, Call, Email, FileAsset, Meeting, Note, Task

    for model in (Activity, Task, Note, Call, Meeting, Email, FileAsset):
        db.session.query(model).filter(model.lead_id == lead.id, model.contact_id.is_(None)).update(
            {"contact_id": contact.id, **({"company_id": company.id} if company else {})}, synchronize_session=False)
    activities.log_activity("converted", f"Lead converted to contact{' and deal' if deal else ''}", lead_id=lead.id, contact_id=contact.id,
                            company_id=company.id if company else None, deal_id=deal.id if deal else None)
    audit.record("lead.converted", entity_type="lead", entity_id=lead.id, summary=f"Converted lead “{lead.name}”",
                 after={"contact_id": str(contact.id), "deal_id": str(deal.id) if deal else None})
    analytics.track("lead_converted")
    db.session.commit()
    return ok({"lead_id": str(lead.id), "contact_id": str(contact.id), "company_id": str(company.id) if company else None,
               "deal_id": str(deal.id) if deal else None})


@bp.get("/facets")
@protect("leads.read")
def facets():
    q = db.session.query(Lead.source, func.count()).filter(Lead.workspace_id == g.workspace.id, Lead.deleted_at.is_(None)).group_by(Lead.source).all()
    return ok({"sources": sorted([s for s, _ in q if s])})
