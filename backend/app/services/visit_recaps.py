"""Visit recap: after a site visit the buyer gets one WhatsApp link with the flats they saw, the rep's photos, a side-by-side
comparison, the prices on record and a "hold this flat" button. The family opens the same page at home, no login needed.

The page is read-only and lives behind an unguessable token. "Hold this flat" only asks the rep to hold it: the flat's
status never changes from the public page."""
from __future__ import annotations

import datetime as dt
import secrets
import uuid

from flask import current_app, g
from sqlalchemy import or_

from app.core.errors import ApiError
from app.extensions import db
from app.models import (
    Contact,
    Deal,
    FileAsset,
    Lead,
    Meeting,
    Project,
    Task,
    Tower,
    Unit,
    User,
    VisitRecap,
    Workspace,
)
from app.models.base import utcnow
from app.services import activities, inventory, notifications
from app.services import comparison as cmp

MAX_FLATS = cmp.MAX_FLATS
MAX_PHOTOS = 12
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
DOC_KINDS = {"price_list": "Price list", "brochure": "Brochure", "floor_plan": "Floor plan"}
TAKEN = ("booked", "sold", "rented", "self_occupied")  # no point asking to hold these
HOLD_REPEAT = dt.timedelta(minutes=10)  # a second tap on the same flat within this window is the same request


def new_token() -> str:
    return secrets.token_urlsafe(24)


def public_url(r: VisitRecap) -> str:
    return f"{current_app.config['WEB_ORIGIN']}/v/{r.token}"


def _ids(raw) -> list[uuid.UUID]:
    return [uuid.UUID(str(x)) for x in raw or []]


# ---- what the rep picks --------------------------------------------------------------------------------------------

def check_units(ids: list[uuid.UUID]) -> list[str]:
    ids = list(dict.fromkeys(ids))
    if len(ids) > MAX_FLATS:
        raise ApiError(422, "validation_error", f"A recap can show up to {MAX_FLATS} flats", {"unit_ids": f"Up to {MAX_FLATS} flats"})
    if ids:
        found = {r[0] for r in db.session.query(Unit.id).filter(Unit.id.in_(ids), Unit.workspace_id == g.workspace.id, Unit.deleted_at.is_(None))}
        if len(found) != len(ids):
            raise ApiError(404, "not_found", "One of these flats no longer exists. Remove it and try again.")
    return [str(i) for i in ids]


def check_photos(ids: list[uuid.UUID]) -> list[str]:
    ids = list(dict.fromkeys(ids))
    if len(ids) > MAX_PHOTOS:
        raise ApiError(422, "validation_error", f"Add up to {MAX_PHOTOS} photos", {"photo_ids": f"Up to {MAX_PHOTOS} photos"})
    if ids:
        rows = db.session.query(FileAsset.id, FileAsset.mime_type).filter(FileAsset.id.in_(ids), FileAsset.workspace_id == g.workspace.id,
                                                                          FileAsset.deleted_at.is_(None)).all()
        if len(rows) != len(ids):
            raise ApiError(404, "not_found", "One of these photos was deleted. Remove it and try again.")
        if any(m not in IMAGE_TYPES for _, m in rows):
            raise ApiError(422, "validation_error", "Only photos (JPG, PNG or WebP) can go on the recap.", {"photo_ids": "Not an image"})
    return [str(i) for i in ids]


def suggested_units(m: Meeting) -> list[str]:
    """The flat booked for the visit, plus any other flat logged as visited by this buyer on the same day."""
    out = [str(m.unit_id)] if m.unit_id else []
    from app.models import UnitEvent

    who = [c for c in (UnitEvent.lead_id == m.lead_id if m.lead_id else None, UnitEvent.contact_id == m.contact_id if m.contact_id else None) if c is not None]
    if who:
        day = m.starts_at.replace(hour=0, minute=0, second=0, microsecond=0)
        rows = db.session.query(UnitEvent.unit_id).filter(UnitEvent.workspace_id == m.workspace_id, UnitEvent.type == "visit", or_(*who),
                                                          UnitEvent.created_at >= day - dt.timedelta(days=1), UnitEvent.created_at < day + dt.timedelta(days=2)) \
            .order_by(UnitEvent.created_at).all()
        out += [str(r[0]) for r in rows]
    return list(dict.fromkeys(out))[:MAX_FLATS]


# ---- the buyer -----------------------------------------------------------------------------------------------------

def buyer(r: VisitRecap) -> tuple[str, Lead | Contact] | None:
    """Who the recap goes to: the lead, else the client (a deal's client counts)."""
    if r.lead_id:
        lead = db.session.get(Lead, r.lead_id)
        if lead and not lead.deleted_at:
            if lead.converted_contact_id:  # a converted lead's WhatsApp lives on the client
                c = db.session.get(Contact, lead.converted_contact_id)
                if c and not c.deleted_at and c.phone:
                    return "contact", c
            return "lead", lead
    deal = db.session.get(Deal, r.deal_id) if r.deal_id else None
    cid = r.contact_id or (deal.contact_id if deal else None)
    if cid:
        c = db.session.get(Contact, cid)
        if c and not c.deleted_at:
            return "contact", c
    return None


def default_message(r: VisitRecap, rep_name: str) -> str:
    who = buyer(r)
    first = who[1].first_name if who else None
    p = db.session.get(Project, r.project_id) if r.project_id else None
    return (f"Hi {first or 'there'}, thank you for visiting{f' {p.name}' if p else ''} today. Here are the flats you saw, with photos, prices "
            f"and a side-by-side comparison, so you can go over them with your family. Tap \"Hold this flat\" on the one you like and I'll "
            f"get back to you right away.\n\n{rep_name}")


# ---- views ---------------------------------------------------------------------------------------------------------

def serialize(r: VisitRecap) -> dict:
    """The rep's view of a recap."""
    units = {u.id: u for u in db.session.query(Unit).filter(Unit.id.in_(_ids(r.unit_ids))).all()} if r.unit_ids else {}
    towers = {t.id: t.name for t in db.session.query(Tower).filter(Tower.id.in_({u.tower_id for u in units.values()}))} if units else {}
    projects = {p.id: p.name for p in db.session.query(Project).filter(Project.id.in_({u.project_id for u in units.values()}))} if units else {}
    flats = [{"id": str(u.id), "number": u.number, "where": " · ".join(x for x in (towers.get(u.tower_id), projects.get(u.project_id)) if x)}
             for u in (units.get(i) for i in _ids(r.unit_ids)) if u is not None]
    photos = {f.id: f for f in db.session.query(FileAsset).filter(FileAsset.id.in_(_ids(r.photo_ids)), FileAsset.deleted_at.is_(None))} if r.photo_ids else {}
    who = buyer(r)
    return {**r.to_dict(), "url": public_url(r), "flats": flats,
            "photos": [{"id": str(f.id), "filename": f.filename} for f in (photos.get(i) for i in _ids(r.photo_ids)) if f is not None],
            "buyer": {"type": who[0], "id": str(who[1].id), "name": who[1].name} if who else None}


def _documents(units: list[Unit]) -> list[FileAsset]:
    if not units:
        return []
    uids, pids = {u.id for u in units}, {u.project_id for u in units}
    return db.session.query(FileAsset).filter(FileAsset.workspace_id == units[0].workspace_id, FileAsset.deleted_at.is_(None), FileAsset.doc_kind.in_(DOC_KINDS),
                                              or_(FileAsset.unit_id.in_(uids), FileAsset.project_id.in_(pids) & FileAsset.unit_id.is_(None))) \
        .order_by(FileAsset.created_at.desc()).limit(10).all()


def shared_file_ids(r: VisitRecap) -> set[uuid.UUID]:
    """Every file the public page may serve: the rep's photos and the brochures / price lists of the flats shown."""
    units = db.session.query(Unit).filter(Unit.id.in_(_ids(r.unit_ids)), Unit.deleted_at.is_(None)).all() if r.unit_ids else []
    return set(_ids(r.photo_ids)) | {f.id for f in _documents(units)}


def public_view(r: VisitRecap) -> dict:
    """What the family sees. No phone numbers, no internal notes: names, flats, photos and listed prices only."""
    ws = db.session.get(Workspace, r.workspace_id)
    rep = db.session.get(User, r.created_by) if r.created_by else None
    who = buyer(r)
    units = db.session.query(Unit).filter(Unit.id.in_(_ids(r.unit_ids)), Unit.deleted_at.is_(None)).all() if r.unit_ids else []
    order = {str(i): n for n, i in enumerate(r.unit_ids or [])}
    units.sort(key=lambda u: order.get(str(u.id), 99))
    table = cmp.build(units) if units else {"flats": [], "rows": []}
    by_key = {row["key"]: row for row in table["rows"]}
    meeting = db.session.get(Meeting, r.meeting_id) if r.meeting_id else None
    project = db.session.get(Project, r.project_id) if r.project_id else (db.session.get(Project, units[0].project_id) if units else None)
    held = {h["unit_id"] for h in r.hold_requests or []}
    flats = []
    for i, (u, f) in enumerate(zip(units, table["flats"])):
        def val(key, i=i):
            row = by_key.get(key)
            return row["values"][i] if row and row["values"][i] != "—" else None

        flats.append({**f, "bhk": u.bhk, "area": val("area"), "floor": val("floor"), "facing": val("facing"), "price": val("price"), "rate": val("rate"),
                      "rent": val("rent"), "availability": val("status"), "can_hold": u.status not in TAKEN, "hold_requested": str(u.id) in held})
    docs = _documents(units)
    return {
        "workspace": ws.name if ws else None,
        "rep": {"name": rep.name if rep else None, "job_role": rep.job_role if rep else None},
        "buyer_first_name": who[1].first_name if who else None,
        "visited_on": (meeting.starts_at if meeting else r.created_at).isoformat(),
        "project": {"name": project.name, "location": ", ".join(x for x in (project.sector, project.locality, project.city) if x) or None,
                    "developer": project.developer, "rera_id": project.rera_id, "address": project.address} if project else None,
        "message": r.message,
        "flats": flats,
        "comparison": table if len(units) >= 2 else None,
        "photos": [str(i) for i in r.photo_ids or []],
        "documents": [{"id": str(d.id), "kind": d.doc_kind, "label": DOC_KINDS.get(d.doc_kind, "Document"), "filename": d.filename, "mime_type": d.mime_type} for d in docs],
        "has_price_list": any(d.doc_kind == "price_list" for d in docs),
    }


def record_view(r: VisitRecap) -> None:
    now = utcnow()
    first = r.sent_at is not None and (r.first_viewed_at is None or r.first_viewed_at < r.sent_at)
    r.views = (r.views or 0) + 1
    r.last_viewed_at = now
    if first:  # the first open after it was sent (earlier opens were the rep checking it)
        r.first_viewed_at = now
        activities.log_activity("visit_recap", "Visit recap opened by the buyer", workspace_id=r.workspace_id, user_id=None,
                                data={"visit_recap_id": str(r.id)}, lead_id=r.lead_id, contact_id=r.contact_id, deal_id=r.deal_id, touch=False)


# ---- hold request --------------------------------------------------------------------------------------------------

def request_hold(r: VisitRecap, unit_id: uuid.UUID, name: str | None, note: str | None) -> dict:
    """The buyer tapped "Hold this flat". Tells the rep (notification + urgent task + timeline); the flat itself is untouched."""
    if str(unit_id) not in {str(x) for x in r.unit_ids or []}:
        raise ApiError(404, "not_found", "This flat isn't part of your recap.")
    unit = db.session.query(Unit).filter(Unit.id == unit_id, Unit.deleted_at.is_(None)).one_or_none()
    if unit is None:
        raise ApiError(404, "not_found", "This flat isn't available any more.")
    if unit.status in TAKEN:
        raise ApiError(409, "flat_taken", "Sorry, this flat has just been booked. Your sales contact will suggest similar ones.")
    now = utcnow()
    for h in r.hold_requests or []:
        if h["unit_id"] == str(unit_id) and dt.datetime.fromisoformat(h["at"]) > now - HOLD_REPEAT:
            return {"status": "already_requested"}
    who = buyer(r)
    buyer_name = (name or "").strip() or (who[1].name if who else "The buyer")
    label = cmp.build([unit])["flats"][0]
    flat = f"{label['title']}" + (f" ({label['subtitle']})" if label["subtitle"] else "")
    r.hold_requests = [*(r.hold_requests or []), {"unit_id": str(unit_id), "at": now.isoformat(), "name": (name or "").strip()[:120] or None,
                                                   "note": (note or "").strip()[:500] or None}]
    rep_ids = {r.created_by}
    if who and getattr(who[1], "owner_id", None):
        rep_ids.add(who[1].owner_id)
    links = {"lead_id": r.lead_id, "contact_id": r.contact_id, "deal_id": r.deal_id, "company_id": r.company_id}
    title = f"{buyer_name} asked you to hold {flat}"
    body = ((note or "").strip() or "Sent from the visit recap.") + " The flat is not on hold yet: put it on hold from the tower if you agree."
    assignee = r.created_by or (who[1].owner_id if who else None)
    task = Task(workspace_id=r.workspace_id, title=f"Hold request: {flat} for {buyer_name}"[:240], description=body, assignee_id=assignee, created_by=None,
                kind="follow_up", priority="urgent", due_at=now + dt.timedelta(hours=1), **links)
    db.session.add(task)
    db.session.flush()
    activities.log_activity("visit_recap", title, workspace_id=r.workspace_id, user_id=None, body=(note or "").strip() or None,
                            data={"visit_recap_id": str(r.id), "unit_id": str(unit_id), "hold_request": True}, **links)
    inventory.log_event(unit, "hold_request", note=f"{buyer_name} asked to hold this flat from the visit recap", lead_id=r.lead_id, contact_id=r.contact_id)
    link = f"/app/leads/{r.lead_id}" if r.lead_id else f"/app/contacts/{r.contact_id}" if r.contact_id else f"/app/deals/{r.deal_id}" if r.deal_id else "/app/tasks"
    notifications.notify(r.workspace_id, rep_ids, "task_assigned", title, body=body, link=link,
                         data={"visit_recap_id": str(r.id), "unit_id": str(unit_id), "task_id": str(task.id)})
    return {"status": "requested"}
