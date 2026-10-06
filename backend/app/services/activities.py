from __future__ import annotations

import datetime as dt
from typing import Any

from flask import g, has_request_context

from app.extensions import db
from app.models import Activity, Company, Contact, Deal, Lead
from app.models.base import utcnow

_ENTITY_FK = {"lead": "lead_id", "contact": "contact_id", "company": "company_id", "deal": "deal_id"}
_MODELS = {"lead": Lead, "contact": Contact, "company": Company, "deal": Deal}


def log_activity(
    type_: str, title: str, *, workspace_id=None, body: str | None = None, data: dict | None = None, user_id=None,
    lead_id=None, contact_id=None, company_id=None, deal_id=None, occurred_at: dt.datetime | None = None,
    touch: bool = True, is_demo: bool = False,
) -> Activity:
    if has_request_context():
        workspace_id = workspace_id or (g.workspace.id if getattr(g, "workspace", None) else None)
        user_id = user_id or (g.user.id if getattr(g, "user", None) else None)
    when = occurred_at or utcnow()
    a = Activity(workspace_id=workspace_id, type=type_, title=title[:300], body=body, data=data or {}, user_id=user_id,
                 lead_id=lead_id, contact_id=contact_id, company_id=company_id, deal_id=deal_id, occurred_at=when, is_demo=is_demo)
    db.session.add(a)
    if touch:
        for model, ident in ((Lead, lead_id), (Contact, contact_id), (Company, company_id), (Deal, deal_id)):
            if ident:
                db.session.query(model).filter(model.id == ident).update({"last_activity_at": when}, synchronize_session=False)
    return a


def links_for(entity_type: str, entity: Any) -> dict[str, Any]:
    """FK kwargs so an event on one entity also shows up on the entities it belongs to."""
    out: dict[str, Any] = {_ENTITY_FK[entity_type]: entity.id}
    if entity_type == "contact" and entity.company_id:
        out["company_id"] = entity.company_id
    if entity_type == "deal":
        out["company_id"] = entity.company_id
        out["contact_id"] = entity.contact_id
    return out
