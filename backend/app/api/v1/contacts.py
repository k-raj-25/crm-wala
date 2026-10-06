from __future__ import annotations

from flask import Blueprint, g

from app.core import search_expr
from app.core.crud import CrudResource, users_map
from app.models import Company, Contact
from app.schemas.crm import ContactIn, ContactPatch
from app.services import activities, events, notifications
from app.services.tags import ensure_tags
from app.services.usage import check_limit

bp = Blueprint("contacts", __name__, url_prefix="/api/v1/contacts")


class ContactResource(CrudResource):
    name, entity_type, model = "contacts", "contact", Contact
    create_schema, patch_schema = ContactIn, ContactPatch
    search_cols = [search_expr.CONTACTS]
    sort_fields = {
        "created_at": Contact.created_at, "updated_at": Contact.updated_at, "name": Contact.first_name, "email": Contact.email,
        "last_contacted_at": Contact.last_contacted_at, "last_activity_at": Contact.last_activity_at, "job_title": Contact.job_title,
    }
    filters = {
        "owner_id": ("in", Contact.owner_id), "company_id": ("in", Contact.company_id), "tags": ("array", Contact.tags),
        "created_at": ("date", Contact.created_at), "last_contacted_at": ("date", Contact.last_contacted_at),
    }
    refs = {"owner_id": "member", "company_id": Company}
    limit_key = "contacts"
    custom_fields = True
    export_columns = [
        ("First name", lambda o: o.first_name), ("Last name", lambda o: o.last_name), ("Email", lambda o: o.email), ("Phone", lambda o: o.phone),
        ("Company", lambda o: o.company.name if o.company else ""), ("Job title", lambda o: o.job_title), ("Owner", lambda o: o._owner_name),
        ("Tags", lambda o: o.tags), ("Location", lambda o: o.location), ("Created", lambda o: o.created_at.isoformat()),
    ]

    def label(self, o):
        return o.name

    def serialize_many(self, objs):
        out = super().serialize_many(objs)
        for d, o in zip(out, objs):
            d["name"] = o.name
            d["company"] = {"id": str(o.company.id), "name": o.company.name} if o.company else None
        return out

    def prepare_create(self, data):
        data["owner_id"] = data.get("owner_id") or g.user.id
        return data

    def after_create(self, c, data):
        ensure_tags(c.tags)
        activities.log_activity("created", "Contact created", contact_id=c.id, company_id=c.company_id)
        if c.owner_id != g.user.id:
            notifications.notify(g.workspace.id, [c.owner_id], "task_assigned", f"Contact assigned: {c.name}", None, f"/app/contacts/{c.id}", exclude_user_id=g.user.id)

    def after_update(self, c, before, changes):
        if "tags" in changes:
            ensure_tags(c.tags)
        if "owner_id" in changes and before["owner_id"] != (str(c.owner_id) if c.owner_id else None):
            owner = users_map({c.owner_id}).get(c.owner_id)
            activities.log_activity("assigned", f"Assigned to {owner['name'] if owner else 'nobody'}", contact_id=c.id, company_id=c.company_id)
        events.emit("contact.updated", {"contact_id": str(c.id), "changes": list(changes)})


res = ContactResource()
res.register(bp)
