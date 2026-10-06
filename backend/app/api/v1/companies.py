from __future__ import annotations

import re
import uuid

from flask import Blueprint, g
from sqlalchemy import func

from app.core import search_expr
from app.core.auth import protect
from app.core.crud import CrudResource
from app.core.responses import ok
from app.extensions import db
from app.models import Company, Contact, Deal
from app.schemas.crm import CompanyIn, CompanyPatch
from app.services import activities
from app.services.tags import ensure_tags

bp = Blueprint("companies", __name__, url_prefix="/api/v1/companies")


def domain_of(website: str | None) -> str | None:
    if not website:
        return None
    d = re.sub(r"^https?://", "", website.strip().lower()).split("/")[0]
    return d.removeprefix("www.") or None


class CompanyResource(CrudResource):
    name, entity_type, model = "companies", "company", Company
    create_schema, patch_schema = CompanyIn, CompanyPatch
    search_cols = [search_expr.COMPANIES]
    sort_fields = {
        "created_at": Company.created_at, "updated_at": Company.updated_at, "name": Company.name, "industry": Company.industry,
        "size": Company.size, "annual_revenue": Company.annual_revenue, "last_activity_at": Company.last_activity_at,
    }
    filters = {
        "owner_id": ("in", Company.owner_id), "industry": ("in", Company.industry), "size": ("in", Company.size),
        "tags": ("array", Company.tags), "created_at": ("date", Company.created_at),
    }
    refs = {"owner_id": "member"}
    custom_fields = True
    export_columns = [
        ("Name", lambda o: o.name), ("Website", lambda o: o.website), ("Industry", lambda o: o.industry), ("Size", lambda o: o.size),
        ("Location", lambda o: o.location), ("Annual revenue", lambda o: o.annual_revenue), ("Phone", lambda o: o.phone),
        ("Owner", lambda o: o._owner_name), ("Tags", lambda o: o.tags), ("Created", lambda o: o.created_at.isoformat()),
    ]

    def serialize_many(self, objs):
        out = super().serialize_many(objs)
        if not objs:
            return out
        ids = [o.id for o in objs]
        contacts = dict(db.session.query(Contact.company_id, func.count()).filter(Contact.company_id.in_(ids), Contact.deleted_at.is_(None)).group_by(Contact.company_id).all())
        deals = {r[0]: (r[1], float(r[2] or 0)) for r in db.session.query(Deal.company_id, func.count(), func.sum(Deal.value)).filter(
            Deal.company_id.in_(ids), Deal.deleted_at.is_(None), Deal.status == "open").group_by(Deal.company_id).all()}
        for d in out:
            cid = uuid.UUID(d["id"])
            d["contacts_count"] = contacts.get(cid, 0)
            d["open_deals_count"], d["open_deals_value"] = deals.get(cid, (0, 0.0))
        return out

    def prepare_create(self, data):
        data["owner_id"] = data.get("owner_id") or g.user.id
        data["domain"] = domain_of(data.get("website"))
        return data

    def prepare_update(self, obj, changes):
        if "website" in changes:
            changes["domain"] = domain_of(changes["website"])
        return changes

    def after_create(self, c, data):
        ensure_tags(c.tags)
        activities.log_activity("created", "Company created", company_id=c.id)

    def after_update(self, c, before, changes):
        if "tags" in changes:
            ensure_tags(c.tags)


res = CompanyResource()
res.register(bp)


@bp.get("/<uuid:ident>/summary")
@protect("companies.read")
def summary(ident):
    c = res.get_or_404(ident)
    won = db.session.query(func.count(), func.coalesce(func.sum(Deal.value), 0)).filter(Deal.company_id == c.id, Deal.deleted_at.is_(None), Deal.status == "won").one()
    open_ = db.session.query(func.count(), func.coalesce(func.sum(Deal.value), 0)).filter(Deal.company_id == c.id, Deal.deleted_at.is_(None), Deal.status == "open").one()
    contacts = db.session.query(func.count()).filter(Contact.company_id == c.id, Contact.deleted_at.is_(None)).scalar()
    return ok({"won_count": won[0], "won_value": float(won[1]), "open_count": open_[0], "open_value": float(open_[1]), "contacts_count": contacts})
