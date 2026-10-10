"""Notifications, timeline, files, global search."""
from __future__ import annotations

import datetime as dt
import uuid

from flask import Blueprint, Response, current_app, g, request, send_file
from sqlalchemy import func, or_

from app.core import crypto, search_expr
from app.core.auth import protect
from app.core.crud import MAX_PER_PAGE, ensure_ref, parse_date, users_map
from app.core.errors import ApiError, bad_request, not_found
from app.core.responses import created, no_content, ok
from app.extensions import db, limiter
from app.models import Activity, Company, Contact, Deal, FileAsset, Lead, Note, Notification, Task
from app.models.base import utcnow
from app.services import audit, storage
from app.api.v1.crm_helpers import activity_dicts
from app.services.usage import check_limit

bp = Blueprint("activity", __name__, url_prefix="/api/v1")

# ---- notifications ----------------------------------------------------------------------


@bp.get("/notifications")
@protect(allow_restricted=True)
def list_notifications():
    q = db.session.query(Notification).filter(Notification.workspace_id == g.workspace.id, Notification.user_id == g.user.id)
    if request.args.get("unread") == "true":
        q = q.filter(Notification.read_at.is_(None))
    page, per = max(int(request.args.get("page", 1)), 1), min(int(request.args.get("per_page", 30)), MAX_PER_PAGE)
    total = q.count()
    rows = q.order_by(Notification.created_at.desc()).limit(per).offset((page - 1) * per).all()
    unread = db.session.query(func.count(Notification.id)).filter(Notification.workspace_id == g.workspace.id, Notification.user_id == g.user.id,
                                                                  Notification.read_at.is_(None)).scalar()
    return ok([n.to_dict() for n in rows], {"page": page, "per_page": per, "total": total, "unread": unread})


@bp.get("/notifications/unread-count")
@protect(allow_restricted=True)
def unread_count():
    n = db.session.query(func.count(Notification.id)).filter(Notification.workspace_id == g.workspace.id, Notification.user_id == g.user.id,
                                                             Notification.read_at.is_(None)).scalar()
    return ok({"count": n})


@bp.post("/notifications/<uuid:nid>/read")
@protect(allow_restricted=True)
def mark_read(nid):
    n = db.session.query(Notification).filter_by(id=nid, user_id=g.user.id, workspace_id=g.workspace.id).one_or_none()
    if n is None:
        raise not_found("Notification")
    n.read_at = n.read_at or utcnow()
    db.session.commit()
    return ok(n.to_dict())


@bp.post("/notifications/read-all")
@protect(allow_restricted=True)
def mark_all_read():
    db.session.query(Notification).filter(Notification.workspace_id == g.workspace.id, Notification.user_id == g.user.id,
                                          Notification.read_at.is_(None)).update({"read_at": utcnow()})
    db.session.commit()
    return ok({"ok": True})


@bp.delete("/notifications/<uuid:nid>")
@protect(allow_restricted=True)
def delete_notification(nid):
    db.session.query(Notification).filter_by(id=nid, user_id=g.user.id, workspace_id=g.workspace.id).delete()
    db.session.commit()
    return no_content()


# ---- timeline ---------------------------------------------------------------------------

_FK = {"lead": Activity.lead_id, "contact": Activity.contact_id, "company": Activity.company_id, "deal": Activity.deal_id}


@bp.get("/timeline")
@protect("activities.read")
def timeline():
    a = request.args
    q = db.session.query(Activity).filter(Activity.workspace_id == g.workspace.id)
    if a.get("entity"):
        if a["entity"] not in _FK:
            raise bad_request("Unknown entity")
        try:
            q = q.filter(_FK[a["entity"]] == uuid.UUID(a.get("id", "")))
        except ValueError:
            raise bad_request("Invalid id")
    if a.get("types"):
        q = q.filter(Activity.type.in_([t for t in a["types"].split(",") if t]))
    if a.get("user_id"):
        q = q.filter(Activity.user_id == a["user_id"])
    before = parse_date(a.get("before"))
    if before:
        q = q.filter(Activity.occurred_at < before)
    if parse_date(a.get("from")):
        q = q.filter(Activity.occurred_at >= parse_date(a["from"]))
    if parse_date(a.get("to"), end=True):
        q = q.filter(Activity.occurred_at <= parse_date(a["to"], end=True))
    limit = min(int(a.get("limit", 30)), MAX_PER_PAGE)
    rows = q.order_by(Activity.occurred_at.desc(), Activity.id).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    out = activity_dicts(rows)
    return ok(out, {"has_more": has_more, "next_before": rows[-1].occurred_at.isoformat() if rows and has_more else None})


# ---- files ------------------------------------------------------------------------------

@bp.get("/files")
@protect("files.read")
def list_files():
    q = db.session.query(FileAsset).filter(FileAsset.workspace_id == g.workspace.id, FileAsset.deleted_at.is_(None))
    for k in ("lead_id", "contact_id", "company_id", "deal_id", "task_id"):
        if request.args.get(k):
            q = q.filter(getattr(FileAsset, k) == request.args[k])
    rows = q.order_by(FileAsset.created_at.desc()).limit(200).all()
    users = users_map({r.uploaded_by for r in rows})
    return ok([{**r.to_dict(), "uploader": users.get(r.uploaded_by)} for r in rows])


@bp.post("/files")
@protect("files.create")
@limiter.limit("60 per hour")
def upload_file():
    f = request.files.get("file")
    if f is None or not f.filename:
        raise bad_request("Choose a file to upload", "no_file")
    mime = (f.mimetype or "").lower()
    if mime not in current_app.config["ALLOWED_UPLOAD_MIME"]:
        raise ApiError(415, "unsupported_file_type", "That file type isn't allowed. Upload a PDF, image, Office document or text/CSV file.")
    f.stream.seek(0, 2)
    size = f.stream.tell()
    f.stream.seek(0)
    if size == 0:
        raise bad_request("That file is empty", "empty_file")
    from app.services.features import plan_limits
    from app.services.usage import current_usage

    limit_mb = plan_limits(g.workspace).get("storage_mb")
    if limit_mb is not None and current_usage(g.workspace)["storage_mb"] + size / (1024 * 1024) > limit_mb:
        raise ApiError(402, "plan_limit_reached", f"Your plan includes {limit_mb} MB of storage. Upgrade to upload more.", {"limit": "storage_mb"})
    rel = {}
    for k, m in (("lead_id", Lead), ("contact_id", Contact), ("company_id", Company), ("deal_id", Deal), ("task_id", Task)):
        v = request.form.get(k)
        if v:
            try:
                rel[k] = uuid.UUID(v)
            except ValueError:
                raise bad_request(f"Invalid {k}")
            ensure_ref(m, rel[k], k)
    safe_name = "".join(ch for ch in f.filename if ch.isalnum() or ch in " ._-()")[:200] or "file"
    key = storage.new_key(g.workspace.id, safe_name)
    storage.get_storage().put(key, f.stream, mime)
    fa = FileAsset(workspace_id=g.workspace.id, filename=safe_name, storage_key=key, mime_type=mime, size_bytes=size, uploaded_by=g.user.id, **rel)
    db.session.add(fa)
    db.session.flush()
    from app.services import activities

    activities.log_activity("file", f"File attached: {safe_name}", lead_id=rel.get("lead_id"), contact_id=rel.get("contact_id"),
                            company_id=rel.get("company_id"), deal_id=rel.get("deal_id"), data={"file_id": str(fa.id)}, touch=False)
    audit.record("file.uploaded", entity_type="file", entity_id=fa.id, summary=f"Uploaded {safe_name} ({size // 1024} KB)")
    db.session.commit()
    return created(fa.to_dict())


@bp.get("/files/<uuid:fid>/url")
@protect("files.read", allow_restricted=True)
def file_url(fid):
    fa = db.session.query(FileAsset).filter(FileAsset.id == fid, FileAsset.workspace_id == g.workspace.id, FileAsset.deleted_at.is_(None)).one_or_none()
    if fa is None:
        raise not_found("File")
    return ok({"url": storage.get_storage().signed_url(fa.storage_key, fa.filename), "expires_in": 300})


@bp.get("/files/local")
def local_file():
    """Serves local-disk files for dev. Authorised purely by an HMAC signature that expires after 5 minutes."""
    key, exp, sig = request.args.get("key", ""), request.args.get("exp", "0"), request.args.get("sig", "")
    if not exp.isdigit() or int(exp) < dt.datetime.now().timestamp() or not crypto.verify_sig(f"{key}|{exp}", sig):
        raise ApiError(403, "invalid_signature", "This download link is invalid or has expired.")
    path = storage.LocalStorage().open(key)
    if not path.exists():
        raise not_found("File")
    resp = send_file(path, as_attachment=True, download_name=request.args.get("name") or "download")
    resp.headers["Content-Security-Policy"] = "sandbox"
    return resp


@bp.delete("/files/<uuid:fid>")
@protect("files.delete")
def delete_file(fid):
    fa = db.session.query(FileAsset).filter(FileAsset.id == fid, FileAsset.workspace_id == g.workspace.id, FileAsset.deleted_at.is_(None)).one_or_none()
    if fa is None:
        raise not_found("File")
    fa.deleted_at = utcnow()
    audit.record("file.deleted", entity_type="file", entity_id=fa.id, summary=f"Deleted file {fa.filename}")
    db.session.commit()
    return no_content()


# ---- search -----------------------------------------------------------------------------

@bp.get("/search")
@protect()
def search():
    term = request.args.get("q", "").strip()
    if len(term) < 1:
        return ok({})
    like = f"%{term.replace('%', '').replace('_', ' ')[:80]}%"
    ws = g.workspace.id
    can = lambda p: "*" in g.permissions or p in g.permissions  # noqa: E731
    limit = min(int(request.args.get("limit", 5)), 10)
    out: dict[str, list] = {}
    if can("projects.read"):
        from sqlalchemy import literal_column as _lc

        from app.models import Project, Tower, Unit

        rows = db.session.query(Project).filter(Project.workspace_id == ws, Project.deleted_at.is_(None), _lc("(coalesce(projects.name,'') || ' ' || coalesce(projects.developer,'') || ' ' || coalesce(projects.sector,'') || ' ' || coalesce(projects.locality,''))").ilike(like)).order_by(Project.name).limit(limit).all()
        out["projects"] = [{"id": str(r.id), "title": r.name, "subtitle": " · ".join(x for x in (r.developer, r.sector, r.city) if x), "url": f"/app/projects/{r.id}"} for r in rows]
        if can("units.read"):
            rows = db.session.query(Unit, Tower.name, Project.name).join(Tower, Tower.id == Unit.tower_id).join(Project, Project.id == Unit.project_id).filter(
                Unit.workspace_id == ws, Unit.deleted_at.is_(None), Unit.number.ilike(f"{term[:20]}%")).order_by(Unit.number).limit(limit).all()
            out["units"] = [{"id": str(u.id), "title": f"Unit {u.number} · {tn}", "subtitle": f"{pn} · {u.status.replace('_', ' ')}", "url": f"/app/projects/{u.project_id}?tower={u.tower_id}&unit={u.id}"} for u, tn, pn in rows]
    if can("contacts.read"):
        rows = db.session.query(Contact).filter(Contact.workspace_id == ws, Contact.deleted_at.is_(None), search_expr.CONTACTS.ilike(like)).order_by(Contact.updated_at.desc()).limit(limit).all()
        out["contacts"] = [{"id": str(r.id), "title": r.name, "subtitle": " · ".join(x for x in (r.job_title, r.company.name if r.company else None, r.email) if x), "url": f"/app/contacts/{r.id}"} for r in rows]
    if can("leads.read"):
        rows = db.session.query(Lead).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), search_expr.LEADS.ilike(like)).order_by(Lead.updated_at.desc()).limit(limit).all()
        out["leads"] = [{"id": str(r.id), "title": r.name, "subtitle": " · ".join(x for x in (r.company_name, r.email, r.status) if x), "url": f"/app/leads/{r.id}"} for r in rows]
    if can("companies.read"):
        rows = db.session.query(Company).filter(Company.workspace_id == ws, Company.deleted_at.is_(None), search_expr.COMPANIES.ilike(like)).order_by(Company.updated_at.desc()).limit(limit).all()
        out["companies"] = [{"id": str(r.id), "title": r.name, "subtitle": " · ".join(x for x in (r.industry, r.location) if x), "url": f"/app/companies/{r.id}"} for r in rows]
    if can("deals.read"):
        rows = db.session.query(Deal).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), search_expr.DEALS.ilike(like)).order_by(Deal.updated_at.desc()).limit(limit).all()
        out["deals"] = [{"id": str(r.id), "title": r.name, "subtitle": f"{r.stage.name} · {r.currency} {float(r.value):,.0f}", "url": f"/app/deals/{r.id}"} for r in rows]
    if can("tasks.read"):
        rows = db.session.query(Task).filter(Task.workspace_id == ws, Task.deleted_at.is_(None), search_expr.TASKS.ilike(like)).order_by(Task.updated_at.desc()).limit(limit).all()
        out["tasks"] = [{"id": str(r.id), "title": r.title, "subtitle": f"{r.status.replace('_', ' ')}" + (f" · due {r.due_at:%d %b}" if r.due_at else ""), "url": "/app/tasks"} for r in rows]
    if can("notes.read"):
        rows = db.session.query(Note).filter(Note.workspace_id == ws, Note.deleted_at.is_(None), search_expr.NOTES.ilike(like)).order_by(Note.created_at.desc()).limit(limit).all()
        data = [{"id": str(r.id), "title": r.body[:80], "subtitle": "Note", "url": _note_url(r)} for r in rows]
        out["notes"] = data
    if can("activities.read"):
        rows = db.session.query(Activity).filter(Activity.workspace_id == ws, or_(Activity.title.ilike(like), Activity.body.ilike(like))).order_by(Activity.occurred_at.desc()).limit(limit).all()
        out["activities"] = [{"id": str(r.id), "title": r.title, "subtitle": f"{r.occurred_at:%d %b %Y}", "url": _activity_url(r)} for r in rows]
    return ok({k: v for k, v in out.items() if v})


def _note_url(n) -> str:
    for k, p in (("deal_id", "deals"), ("contact_id", "contacts"), ("company_id", "companies"), ("lead_id", "leads")):
        if getattr(n, k):
            return f"/app/{p}/{getattr(n, k)}"
    return "/app/activities"


_activity_url = _note_url


# ---- calendar feed ----------------------------------------------------------------------

@bp.get("/calendar")
@protect("meetings.read")
def calendar_feed():
    """Unified events for the calendar: meetings, scheduled calls, tasks, deadlines and lead follow-ups."""
    from app.models import Call, Meeting

    a = request.args
    start, end = parse_date(a.get("from")), parse_date(a.get("to"), end=True)
    if not start or not end or (end - start).days > 62:
        raise bad_request("Provide from/to dates spanning up to ~2 months")
    ws, mine = g.workspace.id, a.get("mine") == "true"
    events: list[dict] = []
    q = db.session.query(Meeting).filter(Meeting.workspace_id == ws, Meeting.deleted_at.is_(None), Meeting.starts_at >= start, Meeting.starts_at <= end)
    if mine:
        q = q.filter(Meeting.organizer_id == g.user.id)
    for m in q.limit(300):
        events.append({"id": str(m.id), "kind": m.kind if m.kind == "site_visit" else "meeting", "title": m.title, "start": m.starts_at.isoformat(), "end": m.ends_at.isoformat(), "status": m.status,
                       "location": m.meeting_url or m.location, "entity": {"type": "meeting", "id": str(m.id)}})
    if "tasks.read" in g.permissions or "*" in g.permissions:
        q = db.session.query(Task).filter(Task.workspace_id == ws, Task.deleted_at.is_(None), Task.due_at >= start, Task.due_at <= end)
        if mine:
            q = q.filter(Task.assignee_id == g.user.id)
        for t in q.limit(300):
            events.append({"id": str(t.id), "kind": "deadline" if t.kind == "deadline" else "follow_up" if t.kind == "follow_up" else "task", "title": t.title, "start": t.due_at.isoformat(),
                           "end": (t.due_at + dt.timedelta(minutes=30)).isoformat(), "status": t.status, "priority": t.priority, "entity": {"type": "task", "id": str(t.id)}})
        q = db.session.query(Lead).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.status.in_(("new", "contacted", "qualified")), Lead.next_follow_up_at >= start, Lead.next_follow_up_at <= end)
        if mine:
            q = q.filter(Lead.owner_id == g.user.id)
        for l in q.limit(200):
            events.append({"id": str(l.id), "kind": "follow_up", "title": f"Follow up: {l.name}", "start": l.next_follow_up_at.isoformat(), "end": (l.next_follow_up_at + dt.timedelta(minutes=30)).isoformat(),
                           "status": "todo", "entity": {"type": "lead", "id": str(l.id)}})
    q = db.session.query(Call).filter(Call.workspace_id == ws, Call.deleted_at.is_(None), Call.status == "scheduled", Call.scheduled_at >= start, Call.scheduled_at <= end)
    if mine:
        q = q.filter(Call.user_id == g.user.id)
    for c in q.limit(200):
        events.append({"id": str(c.id), "kind": "call", "title": "Scheduled call", "start": c.scheduled_at.isoformat(), "end": (c.scheduled_at + dt.timedelta(minutes=15)).isoformat(), "status": c.status,
                       "entity": {"type": "call", "id": str(c.id)}})
    events.sort(key=lambda e: e["start"])
    return ok(events)
