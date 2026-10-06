"""Import / export / duplicates."""
from __future__ import annotations

import csv
import io
import uuid
import zipfile

from flask import Blueprint, Response, g, request
from pydantic import Field
from sqlalchemy import func

from app.core.auth import protect, require
from app.core.errors import ApiError, bad_request, not_found
from app.core.responses import ok
from app.extensions import db, limiter
from app.models import (
    Activity, Call, Company, Contact, Deal, DuplicateDismissal, Email, FileAsset, ImportJob, Lead, Meeting, Note, Task,
)
from app.models.base import utcnow
from app.schemas.common import Schema, parse
from app.services import audit, importer
from app.services.usage import check_limit

bp = Blueprint("data", __name__, url_prefix="/api/v1")

ENTITY_PERM = {"leads": "leads.create", "contacts": "contacts.create", "companies": "companies.create", "deals": "deals.create"}


def _entity(v: str) -> str:
    if v not in importer.FIELDS:
        raise bad_request("Unknown entity. Use leads, contacts, companies or deals.")
    return v


@bp.get("/import/fields")
@protect("data.import")
def import_fields():
    return ok(importer.FIELDS)


@bp.post("/import/parse")
@protect("data.import")
@limiter.limit("30 per hour")
def import_parse():
    entity = _entity(request.form.get("entity_type", ""))
    require(ENTITY_PERM[entity])
    f = request.files.get("file")
    if f is None:
        raise bad_request("Choose a CSV file", "no_file")
    headers, rows = importer.parse_csv(f.read())
    return ok({"headers": headers, "rows": [dict(zip(headers, r)) for r in rows], "suggested_mapping": importer.suggest_mapping(entity, headers),
               "fields": importer.FIELDS[entity], "filename": f.filename})


class ImportIn(Schema):
    entity_type: str
    mapping: dict[str, str]
    rows: list[dict] = Field(max_length=importer.MAX_ROWS)
    skip_duplicates: bool = True
    filename: str | None = None


@bp.post("/import/validate")
@protect("data.import")
def import_validate():
    d = parse(ImportIn)
    entity = _entity(d.entity_type)
    require(ENTITY_PERM[entity])
    if not any(k in d.mapping for k in ("first_name", "full_name", "name")):
        raise ApiError(422, "validation_error", "Map a name column to continue", {"mapping": "Name column required"})
    return ok(importer.validate_rows(entity, d.mapping, d.rows))


@bp.post("/import/commit")
@protect("data.import")
def import_commit():
    d = parse(ImportIn)
    entity = _entity(d.entity_type)
    require(ENTITY_PERM[entity])
    if entity == "contacts":
        check_limit(g.workspace, "contacts", len(d.rows))
    result = importer.commit(entity, d.mapping, d.rows, skip_duplicates=d.skip_duplicates)
    job = ImportJob(workspace_id=g.workspace.id, entity_type=entity, filename=d.filename, total_rows=result["total"], created_count=result["created"], skipped_count=result["skipped"],
                    error_count=len([e for e in result["errors"] if e.get("severity") != "warning"]), mapping=d.mapping, errors=result["errors"][:200], created_by=g.user.id)
    db.session.add(job)
    audit.record("data.imported", entity_type=entity, summary=f"Imported {result['created']} {entity} from CSV ({result['skipped']} skipped)")
    db.session.commit()
    return ok({**result, "job_id": str(job.id), "errors": result["errors"][:200]})


@bp.get("/import/jobs")
@protect("data.import")
def import_jobs():
    rows = db.session.query(ImportJob).filter_by(workspace_id=g.workspace.id).order_by(ImportJob.created_at.desc()).limit(20).all()
    return ok([r.to_dict(exclude=("errors", "mapping")) for r in rows])


# ---- full export (available even when the trial has expired) ------------------------------

@bp.get("/export/workspace")
@protect("data.export", allow_restricted=True)
def export_workspace():
    from app.api.v1 import companies, contacts, deals, leads, tasks

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for res in (leads.res, contacts.res, companies.res, deals.res, tasks.res):
            q = res.base_query().order_by(res.model.created_at)
            rows = db.session.scalars(q.limit(100000)).unique().all()
            from app.core.crud import _csv_safe, users_map

            users = users_map({getattr(o, res.owner_field) for o in rows} if res.owner_field else set())
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow([h for h, _ in res.export_columns])
            for o in rows:
                o._owner_name = users.get(getattr(o, res.owner_field), {}).get("name") if res.owner_field else None
                w.writerow([_csv_safe(fn(o)) for _, fn in res.export_columns])
            z.writestr(f"{res.name}.csv", out.getvalue())
        notes = db.session.query(Note).filter(Note.workspace_id == g.workspace.id, Note.deleted_at.is_(None)).limit(100000).all()
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["Created", "Body", "Lead", "Contact", "Company", "Deal"])
        from app.core.crud import _csv_safe

        for n in notes:
            w.writerow([n.created_at.isoformat(), _csv_safe(n.body), n.lead_id or "", n.contact_id or "", n.company_id or "", n.deal_id or ""])
        z.writestr("notes.csv", out.getvalue())
    audit.record("data.workspace_exported", entity_type="workspace", entity_id=g.workspace.id, summary="Exported all workspace data")
    db.session.commit()
    return Response(buf.getvalue(), mimetype="application/zip", headers={"Content-Disposition": f'attachment; filename="{g.workspace.slug}-export.zip"'})


# ---- duplicates ---------------------------------------------------------------------------

DUP_MODELS = {"contact": Contact, "lead": Lead}


def _digits(p: str | None) -> str:
    d = "".join(c for c in (p or "") if c.isdigit())
    return d[-10:] if len(d) >= 7 else ""


def _brief(o) -> dict:
    return {"id": str(o.id), "name": o.name, "email": o.email, "phone": o.phone, "company": (o.company.name if getattr(o, "company", None) else getattr(o, "company_name", None)),
            "created_at": o.created_at.isoformat(), "status": getattr(o, "status", None)}


def find_duplicate_groups(entity: str) -> list[dict]:
    model = DUP_MODELS[entity]
    rows = db.session.query(model).filter(model.workspace_id == g.workspace.id, model.deleted_at.is_(None)).order_by(model.created_at).limit(20000).all()
    dismissed = {frozenset((str(d.a_id), str(d.b_id))) for d in db.session.query(DuplicateDismissal).filter_by(workspace_id=g.workspace.id, entity_type=entity)}
    buckets: dict[tuple[str, str], list] = {}
    for o in rows:
        keys = []
        if o.email:
            keys.append(("email", o.email.lower()))
        if _digits(o.phone):
            keys.append(("phone", _digits(o.phone)))
        cname = (o.company.name if getattr(o, "company", None) else getattr(o, "company_name", "")) or ""
        if o.name and cname:
            keys.append(("name+company", f"{o.name.lower()}|{cname.lower()}"))
        for k in keys:
            buckets.setdefault(k, []).append(o)
    groups, seen = [], set()
    for (reason, key), members in buckets.items():
        if len(members) < 2:
            continue
        ids = frozenset(str(m.id) for m in members)
        if ids in seen:
            continue
        pairs = [frozenset((str(a.id), str(b.id))) for i, a in enumerate(members) for b in members[i + 1:]]
        if all(p in dismissed for p in pairs):
            continue
        seen.add(ids)
        groups.append({"reason": {"email": "Same email address", "phone": "Same phone number", "name+company": "Same name and company"}[reason], "key": key, "records": [_brief(m) for m in members]})
    return groups


@bp.get("/duplicates")
@protect("contacts.read")
def duplicates():
    entity = request.args.get("entity_type", "contact")
    if entity not in DUP_MODELS:
        raise bad_request("entity_type must be contact or lead")
    require(f"{entity}s.read")
    return ok(find_duplicate_groups(entity)[:100])


@bp.get("/duplicates/check")
@protect("contacts.read")
def duplicate_check():
    """Inline warning while typing a new record."""
    entity = request.args.get("entity_type", "contact")
    if entity not in DUP_MODELS:
        raise bad_request("entity_type must be contact or lead")
    model = DUP_MODELS[entity]
    email, phone = (request.args.get("email") or "").strip().lower(), _digits(request.args.get("phone"))
    out = []
    if email:
        out += db.session.query(model).filter(model.workspace_id == g.workspace.id, model.deleted_at.is_(None), func.lower(model.email) == email).limit(3).all()
    if phone and not out:
        out += [m for m in db.session.query(model).filter(model.workspace_id == g.workspace.id, model.deleted_at.is_(None), model.phone.isnot(None)).limit(5000) if _digits(m.phone) == phone][:3]
    return ok([_brief(o) for o in out])


class IgnoreIn(Schema):
    entity_type: str = Field(pattern="^(contact|lead)$")
    ids: list[uuid.UUID] = Field(min_length=2, max_length=20)


@bp.post("/duplicates/ignore")
@protect("contacts.update")
def duplicate_ignore():
    d = parse(IgnoreIn)
    ids = sorted(d.ids, key=str)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if not db.session.query(DuplicateDismissal).filter_by(workspace_id=g.workspace.id, entity_type=d.entity_type, a_id=a, b_id=b).first():
                db.session.add(DuplicateDismissal(workspace_id=g.workspace.id, entity_type=d.entity_type, a_id=a, b_id=b))
    db.session.commit()
    return ok({"ignored": True})


class MergeIn(Schema):
    entity_type: str = Field(pattern="^(contact|lead)$")
    primary_id: uuid.UUID
    merge_ids: list[uuid.UUID] = Field(min_length=1, max_length=19)


@bp.post("/duplicates/merge")
@protect("contacts.update")
def duplicate_merge():
    d = parse(MergeIn)
    require(f"{d.entity_type}s.delete")
    model = DUP_MODELS[d.entity_type]
    primary = db.session.query(model).filter(model.id == d.primary_id, model.workspace_id == g.workspace.id, model.deleted_at.is_(None)).one_or_none()
    others = db.session.query(model).filter(model.id.in_(d.merge_ids), model.workspace_id == g.workspace.id, model.deleted_at.is_(None)).all()
    if primary is None or len(others) != len(set(d.merge_ids)) or primary.id in d.merge_ids:
        raise not_found("Records to merge")
    fk = f"{d.entity_type}_id"
    scalar_fields = ["email", "phone", "job_title", "location", "description"] + (["company_id", "avatar_url"] if d.entity_type == "contact" else ["company_name", "source"])
    before = primary.to_dict()
    for o in others:
        for f in scalar_fields:
            if not getattr(primary, f) and getattr(o, f):
                setattr(primary, f, getattr(o, f))
        primary.tags = sorted(set(primary.tags or []) | set(o.tags or []))
        primary.custom = {**(o.custom or {}), **(primary.custom or {})}
        for rel in (Activity, Task, Note, Call, Meeting, Email, FileAsset):
            db.session.query(rel).filter(getattr(rel, fk) == o.id).update({fk: primary.id}, synchronize_session=False)
        if d.entity_type == "contact":
            db.session.query(Deal).filter(Deal.contact_id == o.id).update({"contact_id": primary.id}, synchronize_session=False)
        o.deleted_at = utcnow()
    from app.services import activities

    activities.log_activity("updated", f"Merged {len(others)} duplicate record(s) into this one", **{fk: primary.id})
    audit.record(f"{d.entity_type}.merged", entity_type=d.entity_type, entity_id=primary.id, summary=f"Merged {len(others)} duplicate {d.entity_type}(s) into “{primary.name}”",
                 before=before, after={"merged_ids": [str(o.id) for o in others]})
    db.session.commit()
    return ok({"primary_id": str(primary.id), "merged": len(others)})
