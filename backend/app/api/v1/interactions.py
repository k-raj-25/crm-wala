"""Notes, calls, meetings, emails and email templates (everything that shows on a record's timeline)."""
from __future__ import annotations

import datetime as dt
import uuid

from flask import Blueprint, g, request

from app.core import search_expr
from app.core.auth import protect, require
from app.core.crud import CrudResource
from app.core.errors import ApiError, not_found
from app.core.responses import created, no_content, ok
from app.extensions import db
from app.models import Call, Company, Contact, Deal, Email, EmailTemplate, FileAsset, Lead, Meeting, Note, Task
from app.models.base import utcnow
from app.schemas.common import parse
from app.schemas.crm import (
    CallIn, CallPatch, EmailLogIn, EmailSendIn, EmailTemplateIn, MeetingIn, MeetingPatch, NoteIn, NotePatch,
)
from app.services import activities, audit, events, mailbox, notifications
from app.services.related import attach_related
from app.services.usage import check_limit

notes_bp = Blueprint("notes", __name__, url_prefix="/api/v1/notes")
calls_bp = Blueprint("calls", __name__, url_prefix="/api/v1/calls")
meetings_bp = Blueprint("meetings", __name__, url_prefix="/api/v1/meetings")
emails_bp = Blueprint("emails", __name__, url_prefix="/api/v1/emails")

REL_FILTERS = lambda m: {  # noqa: E731
    "lead_id": ("eq", m.lead_id), "contact_id": ("eq", m.contact_id), "company_id": ("eq", m.company_id), "deal_id": ("eq", m.deal_id),
}
REL_REFS = {"lead_id": Lead, "contact_id": Contact, "company_id": Company, "deal_id": Deal}


def _rel(o) -> dict:
    return dict(lead_id=o.lead_id, contact_id=o.contact_id, company_id=o.company_id, deal_id=o.deal_id)


def _fill_company(data: dict) -> dict:
    """If only a contact/deal is given, also link its company so company timelines aggregate."""
    if data.get("contact_id") and not data.get("company_id"):
        c = db.session.get(Contact, data["contact_id"])
        if c and c.company_id:
            data["company_id"] = c.company_id
    if data.get("deal_id") and not (data.get("company_id") and data.get("contact_id")):
        d = db.session.get(Deal, data["deal_id"])
        if d:
            data.setdefault("company_id", None)
            data["company_id"] = data["company_id"] or d.company_id
            data["contact_id"] = data.get("contact_id") or d.contact_id
    return data


class _Related(CrudResource):
    def serialize_many(self, objs):
        out = super().serialize_many(objs)
        attach_related(objs, out)
        return out


class NoteResource(_Related):
    name, entity_type, model = "notes", "note", Note
    create_schema, patch_schema = NoteIn, NotePatch
    owner_field = "author_id"
    search_cols = [search_expr.NOTES]
    sort_fields = {"created_at": Note.created_at, "updated_at": Note.updated_at}
    filters = REL_FILTERS(Note)
    refs = REL_REFS

    def label(self, o):
        return o.body[:40]

    def serialize_many(self, objs):
        out = super().serialize_many(objs)
        for d in out:
            d["author"] = d.pop("owner")
        return out

    def prepare_create(self, data):
        data["author_id"] = g.user.id
        return _fill_company(data)

    def after_create(self, n, data):
        activities.log_activity("note", "Note added", body=n.body[:500], lead_id=n.lead_id, contact_id=n.contact_id, company_id=n.company_id,
                                deal_id=n.deal_id, data={"note_id": str(n.id)})


class CallResource(_Related):
    name, entity_type, model = "calls", "call", Call
    create_schema, patch_schema = CallIn, CallPatch
    owner_field = "user_id"
    sort_fields = {"created_at": Call.created_at, "occurred_at": Call.occurred_at, "scheduled_at": Call.scheduled_at}
    default_sort = "-created_at"
    filters = {**REL_FILTERS(Call), "status": ("in", Call.status), "outcome": ("in", Call.outcome), "scheduled_at": ("date", Call.scheduled_at),
               "occurred_at": ("date", Call.occurred_at), "user_id": ("in", Call.user_id)}
    refs = REL_REFS

    def label(self, o):
        return f"call {o.outcome or ''}"

    def prepare_create(self, data):
        data["user_id"] = g.user.id
        if data["status"] == "completed" and not data.get("occurred_at"):
            data["occurred_at"] = utcnow()
        if data["status"] == "scheduled" and not data.get("scheduled_at"):
            raise ApiError(422, "validation_error", "Choose when the call is scheduled", {"scheduled_at": "Required"})
        return _fill_company(data)

    def after_create(self, c, data):
        self._log(c)

    def _log(self, c: Call):
        if c.status == "completed":
            label = (c.outcome or "completed").replace("_", " ")
            activities.log_activity("call", f"Call logged — {label}", body=c.notes, occurred_at=c.occurred_at, lead_id=c.lead_id,
                                    contact_id=c.contact_id, company_id=c.company_id, deal_id=c.deal_id, data={"call_id": str(c.id), "outcome": c.outcome})
            mailbox.touch_contacted(c, c.occurred_at or utcnow())
            if c.outcome == "follow_up_required":
                t = Task(workspace_id=g.workspace.id, title="Follow up after call", assignee_id=g.user.id, created_by=g.user.id, kind="follow_up",
                         due_at=utcnow() + dt.timedelta(days=1), priority="high", lead_id=c.lead_id, contact_id=c.contact_id,
                         company_id=c.company_id, deal_id=c.deal_id)
                db.session.add(t)
        elif c.status == "scheduled":
            activities.log_activity("call", "Call scheduled", occurred_at=c.scheduled_at, lead_id=c.lead_id, contact_id=c.contact_id,
                                    company_id=c.company_id, deal_id=c.deal_id, data={"call_id": str(c.id)}, touch=False)

    def prepare_update(self, c, changes):
        if changes.get("status") == "completed" and c.status != "completed" and not changes.get("occurred_at") and not c.occurred_at:
            changes["occurred_at"] = utcnow()
        return changes

    def after_update(self, c, before, changes):
        if before["status"] == "scheduled" and c.status == "completed":
            self._log(c)


class MeetingResource(_Related):
    name, entity_type, model = "meetings", "meeting", Meeting
    create_schema, patch_schema = MeetingIn, MeetingPatch
    owner_field = "organizer_id"
    sort_fields = {"created_at": Meeting.created_at, "starts_at": Meeting.starts_at}
    default_sort = "starts_at"
    filters = {**REL_FILTERS(Meeting), "status": ("in", Meeting.status), "starts_at": ("date", Meeting.starts_at), "organizer_id": ("in", Meeting.organizer_id)}
    refs = REL_REFS

    def label(self, o):
        return o.title

    def prepare_create(self, data):
        data["organizer_id"] = g.user.id
        return _fill_company(data)

    def after_create(self, m, data):
        activities.log_activity("meeting", f"Meeting scheduled: {m.title}", occurred_at=m.starts_at, lead_id=m.lead_id, contact_id=m.contact_id,
                                company_id=m.company_id, deal_id=m.deal_id, data={"meeting_id": str(m.id)}, touch=False)

    def after_update(self, m, before, changes):
        if before["status"] != "completed" and m.status == "completed":
            activities.log_activity("meeting", f"Meeting completed: {m.title}", body=m.summary, lead_id=m.lead_id, contact_id=m.contact_id,
                                    company_id=m.company_id, deal_id=m.deal_id, data={"meeting_id": str(m.id)})
            mailbox.touch_contacted(m, utcnow())


class EmailResource(_Related):
    name, entity_type, model = "emails", "email", Email
    create_schema, patch_schema = EmailLogIn, EmailLogIn
    owner_field = "user_id"
    sort_fields = {"created_at": Email.created_at, "sent_at": Email.sent_at}
    filters = {**REL_FILTERS(Email), "status": ("in", Email.status), "direction": ("in", Email.direction), "user_id": ("in", Email.user_id)}
    refs = REL_REFS
    search_cols = [Email.subject]

    def label(self, o):
        return o.subject

    def prepare_create(self, data):
        data = _fill_company(data)
        if not any(data.get(k) for k in ("lead_id", "contact_id", "company_id", "deal_id")):
            addr = [data["from_address"]] if data.get("from_address") else data.get("to_addresses", [])
            data.update(mailbox.match_records(addr))
        data.update(user_id=g.user.id, status="received" if data["direction"] == "inbound" else "sent", sent_at=utcnow(),
                    to_addresses=data.get("to_addresses") or [])
        return data

    def after_create(self, e, data):
        activities.log_activity("email", f"Email {'received' if e.direction == 'inbound' else 'logged'}: {e.subject}", body=(e.body or "")[:500],
                                lead_id=e.lead_id, contact_id=e.contact_id, company_id=e.company_id, deal_id=e.deal_id, data={"email_id": str(e.id)})

    def register(self, bp):
        n = self.name
        bp.add_url_rule("", "emails_list", protect("emails.read")(self.list), methods=["GET"])
        bp.add_url_rule("/<uuid:ident>", "emails_get", protect("emails.read")(self.get), methods=["GET"])
        bp.add_url_rule("/<uuid:ident>", "emails_delete", protect("emails.delete")(self.delete), methods=["DELETE"])
        bp.add_url_rule("/log", "emails_log", protect("emails.create")(self.create), methods=["POST"])


for resource, bp_ in ((NoteResource(), notes_bp), (CallResource(), calls_bp), (MeetingResource(), meetings_bp)):
    resource.register(bp_)
email_res = EmailResource()
email_res.register(emails_bp)


@emails_bp.post("/send")
@protect("emails.create")
def send_email():
    data = parse(EmailSendIn)
    check_limit(g.workspace, "emails_month", len(data.to))
    related = _fill_company({k: getattr(data, k) for k in ("lead_id", "contact_id", "company_id", "deal_id")})
    for f, m in REL_REFS.items():
        if related.get(f):
            from app.core.crud import ensure_ref

            ensure_ref(m, related[f], f)
    if data.scheduled_at and data.scheduled_at <= utcnow():
        raise ApiError(422, "validation_error", "Schedule time must be in the future", {"scheduled_at": "Must be in the future"})
    sender_name = g.user.name
    ctx = {"sender_name": sender_name}
    if related.get("contact_id"):
        c = db.session.get(Contact, related["contact_id"])
        ctx.update(first_name=c.first_name, last_name=c.last_name or "", company=c.company.name if c.company else "")
    elif related.get("lead_id"):
        l = db.session.get(Lead, related["lead_id"])
        ctx.update(first_name=l.first_name, last_name=l.last_name or "", company=l.company_name or "")
    email = mailbox.send_crm_email(
        g.user, to=data.to, cc=data.cc, subject=mailbox.merge_fields(data.subject, ctx), body=mailbox.merge_fields(data.body, ctx),
        track=data.track, scheduled_at=data.scheduled_at, related=related, attachment_file_ids=[str(i) for i in data.attachment_file_ids])
    audit.record("email.sent" if not data.scheduled_at else "email.scheduled", entity_type="email", entity_id=email.id,
                 summary=f"Email “{email.subject}” {'sent' if not data.scheduled_at else 'scheduled'} to {', '.join(email.to_addresses)}")
    db.session.commit()
    return created(email_res.serialize(email))


@emails_bp.post("/<uuid:ident>/cancel")
@protect("emails.update")
def cancel_scheduled(ident):
    e = email_res.get_or_404(ident)
    if e.status != "scheduled":
        raise ApiError(409, "not_scheduled", "Only scheduled emails can be canceled")
    e.deleted_at = utcnow()
    db.session.commit()
    return no_content()


# ---- templates ---------------------------------------------------------------------------

@emails_bp.get("/templates")
@protect("emails.read")
def list_templates():
    rows = db.session.query(EmailTemplate).filter_by(workspace_id=g.workspace.id).order_by(EmailTemplate.name).all()
    return ok([r.to_dict() for r in rows])


@emails_bp.post("/templates")
@protect("emails.create")
def create_template():
    d = parse(EmailTemplateIn)
    t = EmailTemplate(workspace_id=g.workspace.id, created_by=g.user.id, **d.model_dump())
    db.session.add(t)
    db.session.commit()
    return created(t.to_dict())


@emails_bp.patch("/templates/<uuid:tid>")
@protect("emails.update")
def update_template(tid):
    t = db.session.query(EmailTemplate).filter_by(id=tid, workspace_id=g.workspace.id).one_or_none()
    if t is None:
        raise not_found("Template")
    d = parse(EmailTemplateIn)
    t.name, t.subject, t.body = d.name, d.subject, d.body
    db.session.commit()
    return ok(t.to_dict())


@emails_bp.delete("/templates/<uuid:tid>")
@protect("emails.delete")
def delete_template(tid):
    t = db.session.query(EmailTemplate).filter_by(id=tid, workspace_id=g.workspace.id).one_or_none()
    if t is None:
        raise not_found("Template")
    db.session.delete(t)
    db.session.commit()
    return no_content()
