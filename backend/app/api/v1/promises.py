"""Promise ledger: reps record what they promised a buyer, managers approve or reject it, the booking form prints the approved ones."""
from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Literal

from flask import Blueprint, Response, g, request
from pydantic import Field
from sqlalchemy import func

from app.core.auth import protect, require
from app.core.crud import CrudResource
from app.core.errors import ApiError, bad_request, conflict
from app.core.responses import ok
from app.extensions import db
from app.models import Contact, Deal, Lead, Promise, Unit
from app.models.base import utcnow
from app.schemas.common import Schema, parse, patchify
from app.services import activities, audit, notifications, privacy
from app.services import promises as svc

bp = Blueprint("promises", __name__, url_prefix="/api/v1/promises")
bp.after_request(privacy.mask_response)  # source_text quotes chats and notes, which can carry phone numbers

Kind = Literal["discount", "parking", "fittings", "possession", "payment_plan", "waiver", "other"]
Source = Literal["manual", "whatsapp", "call", "visit", "note", "chat"]


class PromiseIn(Schema):
    title: str = Field(min_length=2, max_length=200)
    kind: Kind = "other"
    details: str | None = Field(default=None, max_length=4000)
    value: decimal.Decimal | None = Field(default=None, ge=0, le=10**13)
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    promised_by: uuid.UUID | None = None
    promised_on: dt.date | None = None
    source: Source = "manual"
    source_text: str | None = Field(default=None, max_length=2000)


PromisePatch = patchify(PromiseIn, "PromisePatch")
EDITABLE = {"title", "kind", "details", "value", "unit_id", "promised_by", "promised_on"}


class DecisionIn(Schema):
    note: str | None = Field(default=None, max_length=500)


class PromiseResource(CrudResource):
    name, entity_type, model = "promises", "promise", Promise
    create_schema, patch_schema = PromiseIn, PromisePatch
    owner_field = None
    search_cols = [Promise.title, Promise.details]
    sort_fields = {"created_at": Promise.created_at, "decided_at": Promise.decided_at, "promised_on": Promise.promised_on, "value": Promise.value}
    filters = {"status": ("in", Promise.status), "kind": ("in", Promise.kind), "promised_by": ("in", Promise.promised_by),
               "lead_id": ("in", Promise.lead_id), "deal_id": ("in", Promise.deal_id), "contact_id": ("in", Promise.contact_id)}
    refs = {"lead_id": Lead, "contact_id": Contact, "deal_id": Deal, "unit_id": Unit, "promised_by": "member"}
    export_columns = [("Promise", lambda o: o.title), ("Type", lambda o: svc.KINDS.get(o.kind)), ("Value", lambda o: o.value),
                      ("Status", lambda o: svc.STATUSES.get(o.status)), ("Promised on", lambda o: o.promised_on), ("Details", lambda o: o.details)]

    def label(self, o):
        return o.title

    def extra_filters(self, q):
        rec = request.args.get("record", "")  # "lead:<id>": everything promised to this buyer, across their lead, client and deal
        if rec:
            entity, _, raw = rec.partition(":")
            try:
                ident = uuid.UUID(raw)
            except ValueError:
                raise bad_request("Invalid record")
            svc.get_record(entity, ident)
            q = q.where(svc.group_filter(entity, ident))
        return q

    def serialize_many(self, objs):
        return svc.serialize(objs)

    def prepare_create(self, data):
        if not (data.get("lead_id") or data.get("contact_id") or data.get("deal_id")):
            raise ApiError(422, "validation_error", "Choose the buyer this promise was made to", {"lead_id": "Required"})
        self.validate_refs(data)  # before following the links, so they only ever lead to this workspace's records
        data["promised_by"] = data.get("promised_by") or g.user.id
        data["promised_on"] = data.get("promised_on") or utcnow().date()
        data["created_by"], data["status"] = g.user.id, "pending"
        return svc.fill_links(data)

    def after_create(self, p, data):
        who = svc.serialize([p])[0]
        title = f"{who['promised_by_name'] or 'A teammate'} promised {who['buyer_name'] or 'a buyer'}: {p.title}"
        activities.log_activity("promise", title, body=p.details, data={"promise_id": str(p.id), "status": "pending"},
                                lead_id=p.lead_id, contact_id=p.contact_id, deal_id=p.deal_id)
        notifications.notify(g.workspace.id, svc.approver_ids(g.workspace.id), "promise", f"{title}. Approve or reject?",
                             body=p.details, link="/app/promises", data={"promise_id": str(p.id)}, exclude_user_id=g.user.id)

    def prepare_update(self, p, changes):
        if p.status != "pending":
            raise conflict("Only promises waiting for approval can be edited. Cancel this one and record a new promise instead.", "promise_decided")
        extra = set(changes) - EDITABLE
        if extra:
            raise bad_request("These details can't be changed: " + ", ".join(sorted(extra)))
        if "title" in changes and not changes["title"]:
            raise bad_request("A promise needs a title")
        return changes

    def before_delete(self, p):
        if p.status == "approved":
            raise conflict("Approved promises can't be deleted. Cancel it with a reason so the record stays.", "promise_decided")
        if p.created_by != g.user.id and not svc.can_approve():
            raise ApiError(403, "permission_denied", "Only the person who recorded this promise, or a manager, can delete it.")


res = PromiseResource()
res.register(bp)


def _decide(ident, status: str, verb: str):
    p = res.get_or_404(ident)
    d = parse(DecisionIn, request.get_json(silent=True) or {})
    if status in ("approved", "rejected"):
        require("promises.approve")
        if p.status != "pending":
            raise conflict(f"This promise is already {svc.STATUSES[p.status].lower()}.", "promise_decided")
    else:  # cancelled: the rep who recorded a pending promise, or a manager for any open one
        if p.status in ("rejected", "cancelled"):
            raise conflict(f"This promise is already {svc.STATUSES[p.status].lower()}.", "promise_decided")
        if not svc.can_approve() and not (p.status == "pending" and p.created_by == g.user.id):
            raise ApiError(403, "permission_denied", "Only a manager can cancel an approved promise, or one someone else recorded.")
        if p.status == "approved" and not d.note:
            raise ApiError(422, "validation_error", "Say why the approved promise is being cancelled", {"note": "Required"})
    before = p.status
    p.status, p.decided_by, p.decided_at, p.decision_note = status, g.user.id, utcnow(), d.note
    db.session.flush()
    who = svc.serialize([p])[0]
    summary = f"{verb} promise “{p.title}”" + (f" to {who['buyer_name']}" if who["buyer_name"] else "") + (f" (promised by {who['promised_by_name']})" if who["promised_by_name"] else "")
    audit.record(f"promise.{status}", entity_type="promise", entity_id=p.id, summary=summary, before={"status": before},
                 after={"status": status, "note": d.note})
    activities.log_activity("promise", f"{g.user.name} {verb.lower()} the promise: {p.title}", body=d.note, data={"promise_id": str(p.id), "status": status},
                            lead_id=p.lead_id, contact_id=p.contact_id, deal_id=p.deal_id, touch=False)
    notifications.notify(g.workspace.id, [p.promised_by, p.created_by], "promise", f"{g.user.name} {verb.lower()} “{p.title}”",
                         body=d.note, link=who["url"], data={"promise_id": str(p.id)}, exclude_user_id=g.user.id)
    db.session.commit()
    return ok(svc.serialize([p])[0])


@bp.post("/<uuid:ident>/approve")
@protect("promises.read")
def approve(ident):
    return _decide(ident, "approved", "Approved")


@bp.post("/<uuid:ident>/reject")
@protect("promises.read")
def reject(ident):
    return _decide(ident, "rejected", "Rejected")


@bp.post("/<uuid:ident>/cancel")
@protect("promises.read")
def cancel(ident):
    return _decide(ident, "cancelled", "Cancelled")


@bp.get("/summary")
@protect("promises.read")
def summary():
    rows = dict(db.session.query(Promise.status, func.count()).filter(Promise.workspace_id == g.workspace.id, Promise.deleted_at.is_(None))
                .group_by(Promise.status).all())
    return ok({"counts": {k: rows.get(k, 0) for k in svc.STATUSES}, "can_approve": svc.can_approve(), "kinds": svc.KINDS, "statuses": svc.STATUSES})


@bp.get("/booking-form")
@protect("promises.read")
def booking_form():
    entity, _, raw = request.args.get("record", "").partition(":")
    try:
        ident = uuid.UUID(raw)
    except ValueError:
        raise bad_request("Choose a lead, client or deal")
    require(f"{entity}s.read" if entity in ("lead", "contact", "deal") else "promises.read")
    pdf, name, count = svc.booking_form(entity, ident)
    audit.record("promise.booking_form", entity_type=entity, entity_id=ident, summary=f"Downloaded the booking form with {count} approved promise{'s' if count != 1 else ''}")
    db.session.commit()
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})
