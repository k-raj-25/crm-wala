"""CSV import: parse -> suggest mapping -> validate per row -> commit. Pure functions + a commit that writes in one transaction."""
from __future__ import annotations

import csv
import datetime as dt
import decimal
import io
import re
import uuid
from typing import Any

from flask import g
from pydantic import ValidationError
from sqlalchemy import func

from app.core.errors import ApiError, bad_request
from app.extensions import db
from app.models import Activity, Company, Contact, Deal, Lead, Pipeline, PipelineStage
from app.models.base import utcnow
from app.schemas.crm import CompanyIn, ContactIn, DealIn, LeadIn

MAX_ROWS = 5000
MAX_BYTES = 10 * 1024 * 1024

FIELDS: dict[str, list[dict]] = {
    "leads": [
        {"key": "full_name", "label": "Full name", "hint": "Split into first/last"}, {"key": "first_name", "label": "First name", "required": True},
        {"key": "last_name", "label": "Last name"}, {"key": "email", "label": "Email"}, {"key": "phone", "label": "Phone"},
        {"key": "company_name", "label": "Company"}, {"key": "job_title", "label": "Job title"}, {"key": "source", "label": "Source"},
        {"key": "status", "label": "Status"}, {"key": "location", "label": "Location"}, {"key": "tags", "label": "Tags", "hint": "Comma separated"},
        {"key": "description", "label": "Notes"},
    ],
    "contacts": [
        {"key": "full_name", "label": "Full name", "hint": "Split into first/last"}, {"key": "first_name", "label": "First name", "required": True},
        {"key": "last_name", "label": "Last name"}, {"key": "email", "label": "Email"}, {"key": "phone", "label": "Phone"},
        {"key": "job_title", "label": "Job title"}, {"key": "company", "label": "Company", "hint": "Matched by name or created"},
        {"key": "location", "label": "Location"}, {"key": "tags", "label": "Tags"}, {"key": "description", "label": "Notes"},
    ],
    "companies": [
        {"key": "name", "label": "Company name", "required": True}, {"key": "website", "label": "Website"}, {"key": "industry", "label": "Industry"},
        {"key": "size", "label": "Size"}, {"key": "location", "label": "Location"}, {"key": "annual_revenue", "label": "Annual revenue"},
        {"key": "phone", "label": "Phone"}, {"key": "tags", "label": "Tags"}, {"key": "description", "label": "Notes"},
    ],
    "deals": [
        {"key": "name", "label": "Deal name", "required": True}, {"key": "company", "label": "Company"}, {"key": "contact_email", "label": "Contact email"},
        {"key": "value", "label": "Value"}, {"key": "currency", "label": "Currency"}, {"key": "stage", "label": "Stage", "hint": "Matched by name"},
        {"key": "expected_close_date", "label": "Expected close", "hint": "YYYY-MM-DD"}, {"key": "priority", "label": "Priority"},
        {"key": "source", "label": "Source"}, {"key": "tags", "label": "Tags"}, {"key": "description", "label": "Notes"},
    ],
}
ALIASES = {
    "full_name": ["name", "full name", "fullname", "contact name", "contact"], "first_name": ["first name", "firstname", "given name", "first"],
    "last_name": ["last name", "lastname", "surname", "family name", "last"], "email": ["email address", "e-mail", "mail", "email id"],
    "phone": ["phone number", "mobile", "telephone", "tel", "cell", "contact number"], "company_name": ["company", "organization", "organisation", "account", "employer"],
    "company": ["company name", "organization", "organisation", "account"], "job_title": ["title", "job", "position", "designation", "role"],
    "source": ["lead source", "origin", "channel"], "status": ["lead status", "stage"], "location": ["city", "address", "country", "region"],
    "tags": ["labels", "tag"], "description": ["notes", "note", "comments", "description", "remarks"], "name": ["deal name", "deal", "title", "company name", "account name"],
    "website": ["url", "site", "web", "domain"], "industry": ["sector", "vertical"], "size": ["employees", "company size", "team size"],
    "annual_revenue": ["revenue", "turnover"], "value": ["amount", "deal value", "deal amount", "price"], "stage": ["pipeline stage", "deal stage"],
    "expected_close_date": ["close date", "expected close", "closing date"], "contact_email": ["contact", "email"],
}


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", h.lower().replace("_", " ").replace("-", " ")).strip()


def parse_csv(data: bytes) -> tuple[list[str], list[list[str]]]:
    if len(data) > MAX_BYTES:
        raise ApiError(413, "payload_too_large", "CSV files up to 10 MB are supported.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise bad_request("The file needs a header row and at least one data row.", "empty_csv")
    headers = [h.strip() or f"Column {i + 1}" for i, h in enumerate(rows[0])]
    body = rows[1:]
    if len(body) > MAX_ROWS:
        raise ApiError(413, "too_many_rows", f"Import up to {MAX_ROWS:,} rows at a time. Split your file and import in batches.")
    return headers, [r + [""] * (len(headers) - len(r)) for r in body]


def suggest_mapping(entity: str, headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used: set[str] = set()
    fields = [f["key"] for f in FIELDS[entity]]
    for key in fields:  # exact matches first
        for h in headers:
            if h not in used and _norm(h) == _norm(key):
                mapping[key] = h
                used.add(h)
                break
    for key in fields:
        if key in mapping:
            continue
        for h in headers:
            if h not in used and _norm(h) in ALIASES.get(key, []):
                mapping[key] = h
                used.add(h)
                break
    if "full_name" in mapping and ("first_name" in mapping):
        del mapping["full_name"]
    return mapping


def _row_to_data(entity: str, mapping: dict[str, str], row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field, header in mapping.items():
        v = row.get(header)
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        out[field] = v.strip() if isinstance(v, str) else v
    if "full_name" in out:
        full = out.pop("full_name")
        parts = full.split(None, 1)
        out.setdefault("first_name", parts[0])
        if len(parts) > 1:
            out.setdefault("last_name", parts[1])
    if "tags" in out and isinstance(out["tags"], str):
        out["tags"] = [t.strip() for t in re.split(r"[,;|]", out["tags"]) if t.strip()]
    if "annual_revenue" in out or "value" in out:
        for k in ("annual_revenue", "value"):
            if k in out and isinstance(out[k], str):
                cleaned = re.sub(r"[^\d.\-]", "", out[k])
                out[k] = cleaned or None
    return out


def _schema(entity: str):
    return {"leads": LeadIn, "contacts": ContactIn, "companies": CompanyIn, "deals": DealIn}[entity]


def validate_rows(entity: str, mapping: dict[str, str], rows: list[dict]) -> dict:
    schema = _schema(entity)
    statuses = [s["key"] for s in (g.workspace.settings or {}).get("lead_statuses", [])]
    stage_names = {}
    if entity == "deals":
        for s in db.session.query(PipelineStage).join(Pipeline, Pipeline.id == PipelineStage.pipeline_id).filter(Pipeline.workspace_id == g.workspace.id, Pipeline.is_default.is_(True)):
            stage_names[s.name.lower()] = s
    existing_emails: set[str] = set()
    model = {"leads": Lead, "contacts": Contact}.get(entity)
    if model is not None:
        existing_emails = {e.lower() for (e,) in db.session.query(model.email).filter(model.workspace_id == g.workspace.id, model.deleted_at.is_(None), model.email.isnot(None))}
    errors, valid, seen = [], 0, set()
    for i, raw in enumerate(rows):
        data = _row_to_data(entity, mapping, raw)
        row_errors: dict[str, str] = {}
        norm = {k: v for k, v in data.items() if k not in ("company", "contact_email", "stage")}
        try:
            schema.model_validate(norm)
        except ValidationError as e:
            for err in e.errors():
                row_errors[str(err["loc"][0]) if err["loc"] else "_"] = err["msg"].removeprefix("Value error, ")
        if entity == "leads" and data.get("status") and data["status"].lower() not in statuses:
            row_errors["status"] = f"Unknown status “{data['status']}”"
        if entity == "deals" and data.get("stage") and data["stage"].lower() not in stage_names:
            row_errors["stage"] = f"Unknown stage “{data['stage']}”"
        dup = False
        email = (data.get("email") or "").lower()
        if email and model is not None and not row_errors.get("email"):
            dup = email in existing_emails or email in seen
            seen.add(email)
        for field, msg in row_errors.items():
            errors.append({"row": i, "field": field, "message": msg, "value": data.get(field)})
        if not row_errors:
            valid += 1
        if dup:
            errors.append({"row": i, "field": "email", "message": "Duplicate email — already exists in your CRM or earlier in this file", "severity": "warning", "value": email})
    return {"total": len(rows), "valid": valid, "errors": errors}


def commit(entity: str, mapping: dict[str, str], rows: list[dict], *, skip_duplicates: bool = True) -> dict:
    result = validate_rows(entity, mapping, rows)
    bad_rows = {e["row"] for e in result["errors"] if e.get("severity") != "warning"}
    dup_rows = {e["row"] for e in result["errors"] if e.get("severity") == "warning"}
    ws = g.workspace.id
    created = skipped = 0
    now = utcnow()
    company_cache: dict[str, uuid.UUID] = {}
    default_pipeline = None
    stages: dict[str, PipelineStage] = {}
    first_stage = None
    if entity == "deals":
        default_pipeline = db.session.query(Pipeline).filter_by(workspace_id=ws, is_default=True, deleted_at=None).first()
        sl = db.session.query(PipelineStage).filter_by(pipeline_id=default_pipeline.id).order_by(PipelineStage.position).all()
        stages = {s.name.lower(): s for s in sl}
        first_stage = sl[0]

    def company_id_for(name: str | None):
        if not name:
            return None
        key = name.lower()
        if key in company_cache:
            return company_cache[key]
        c = db.session.query(Company).filter(Company.workspace_id == ws, Company.deleted_at.is_(None), func.lower(Company.name) == key).first()
        if c is None:
            c = Company(workspace_id=ws, name=name, owner_id=g.user.id)
            db.session.add(c)
            db.session.flush()
        company_cache[key] = c.id
        return c.id

    for i, raw in enumerate(rows):
        if i in bad_rows or (skip_duplicates and i in dup_rows):
            skipped += 1
            continue
        d = _row_to_data(entity, mapping, raw)
        if entity == "leads":
            from app.api.v1.leads import rescore

            obj = Lead(workspace_id=ws, owner_id=g.user.id, source=d.get("source") or "import", **{k: v for k, v in LeadIn.model_validate(d).model_dump(exclude_unset=True).items() if k not in ("custom",)})
            db.session.add(obj)
            db.session.flush()
            rescore(obj)
            db.session.add(Activity(workspace_id=ws, type="created", title="Lead imported from CSV", lead_id=obj.id, user_id=g.user.id, occurred_at=now))
        elif entity == "contacts":
            cname = d.pop("company", None)
            data = ContactIn.model_validate(d).model_dump(exclude_unset=True)
            obj = Contact(workspace_id=ws, owner_id=g.user.id, company_id=company_id_for(cname), **{k: v for k, v in data.items() if k != "custom"})
            db.session.add(obj)
            db.session.flush()
            db.session.add(Activity(workspace_id=ws, type="created", title="Contact imported from CSV", contact_id=obj.id, company_id=obj.company_id, user_id=g.user.id, occurred_at=now))
        elif entity == "companies":
            from app.api.v1.companies import domain_of

            data = CompanyIn.model_validate(d).model_dump(exclude_unset=True)
            obj = Company(workspace_id=ws, owner_id=g.user.id, domain=domain_of(data.get("website")), **{k: v for k, v in data.items() if k != "custom"})
            db.session.add(obj)
            db.session.flush()
            db.session.add(Activity(workspace_id=ws, type="created", title="Company imported from CSV", company_id=obj.id, user_id=g.user.id, occurred_at=now))
        else:
            from app.api.v1.deals import apply_stage

            cname, cemail, sname = d.pop("company", None), d.pop("contact_email", None), d.pop("stage", None)
            data = DealIn.model_validate(d).model_dump(exclude_unset=True)
            contact = db.session.query(Contact).filter(Contact.workspace_id == ws, Contact.deleted_at.is_(None), func.lower(Contact.email) == cemail.lower()).first() if cemail else None
            stage = stages.get((sname or "").lower(), first_stage)
            obj = Deal(workspace_id=ws, owner_id=g.user.id, pipeline_id=default_pipeline.id, stage_id=stage.id, company_id=company_id_for(cname) or (contact.company_id if contact else None),
                       contact_id=contact.id if contact else None, **{k: v for k, v in data.items() if k not in ("custom", "probability", "pipeline_id", "stage_id", "company_id", "contact_id")})
            apply_stage(obj, stage)
            db.session.add(obj)
            db.session.flush()
            db.session.add(Activity(workspace_id=ws, type="created", title=f"Deal imported into {stage.name}", deal_id=obj.id, company_id=obj.company_id, contact_id=obj.contact_id, user_id=g.user.id, occurred_at=now))
        created += 1
    result.update(created=created, skipped=skipped)
    return result
