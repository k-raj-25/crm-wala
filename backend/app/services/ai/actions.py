""""Do it for me": the assistant prepares changes as proposals; nothing is written here.

A proposal is a card the user reviews: a title, the before → after of each field (editable), and the exact API calls that
will run when they press Approve. The browser runs those calls with the user's own session, so every existing permission
check, validation rule, audit entry and automation applies exactly as if they had clicked through the screens themselves.
Undo calls are prepared alongside, so an approved change can be reversed for a short while.

Text the assistant read (WhatsApp messages, portal enquiries, notes) can never apply a change by itself: the only way a
proposal becomes a write is a person pressing Approve.
"""
from __future__ import annotations

import datetime as dt
import decimal
import re
import uuid
from typing import Any

from flask import g
from sqlalchemy import func, or_

from app.core.permissions import has_permission
from app.extensions import db
from app.models import Contact, Deal, Lead, Project, Tower, Unit, User, WorkspaceMember
from app.models.base import utcnow
from app.services import inventory

MAX_BULK = 200
LEAD_FIELDS = {
    "first_name": ("First name", "text"), "last_name": ("Last name", "text"), "phone": ("Phone", "text"), "email": ("Email", "text"),
    "status": ("Status", "select"), "owner": ("Owner", "select"), "intent": ("Looking to", "select"), "property_type": ("Property type", "select"),
    "bhk": ("Size", "text"), "budget_min": ("Budget from", "money"), "budget_max": ("Budget up to", "money"), "location": ("Preferred area", "text"),
    "next_follow_up_at": ("Follow-up", "datetime"), "source": ("Source", "text"), "description": ("Notes", "textarea"), "tags": ("Tags", "tags"),
    "project": ("Project", "text"), "unit": ("Flat", "text"), "company_name": ("Company", "text"), "lost_reason": ("Lost reason", "text"),
}
INTENTS = [["buy", "Buy"], ["rent", "Rent"], ["invest", "Invest"], ["sell", "Sell"], ["lease", "Lease out"]]
PROPERTY_TYPES = [["apartment", "Flat"], ["villa", "Villa"], ["plot", "Plot"], ["office", "Office"], ["shop", "Shop"], ["other", "Other"]]


class ActionError(Exception):
    """Shown to the model so it can ask the user a follow-up question."""


# ---- collection -----------------------------------------------------------------------------------------------------

def begin() -> None:
    g.ai_proposals = []


def collected() -> list[dict]:
    return list(getattr(g, "ai_proposals", []) or [])


def _add(p: dict) -> dict:
    if not hasattr(g, "ai_proposals"):
        g.ai_proposals = []
    g.ai_proposals.append(p)
    return {"proposal_id": p["id"], "status": "awaiting_approval", "title": p["title"],
            "note": "Shown to the user as a card with Approve / Edit / Cancel. It is NOT saved until they approve."}


def proposal(kind: str, title: str, *, ops: list[dict], record: dict | None = None, changes: list[dict] | None = None, undo: list[dict] | None = None,
             items: list[dict] | None = None, warning: str | None = None, description: str | None = None, url: str | None = None, extra: dict | None = None) -> dict:
    return {"id": uuid.uuid4().hex[:12], "kind": kind, "title": title, "description": description, "record": record, "changes": changes or [],
            "ops": ops, "undo": undo, "items": items, "warning": warning, "url": url, **(extra or {})}


def _can(p: str) -> bool:
    return has_permission(g.permissions, p)


def _need(p: str, what: str) -> None:
    if not _can(p):
        raise ActionError(f"Your role doesn't allow you to {what}.")


# ---- formatting ---------------------------------------------------------------------------------------------------------

def _tz():
    from zoneinfo import ZoneInfo

    try:
        return ZoneInfo(g.workspace.timezone or "Asia/Kolkata")
    except Exception:
        return dt.timezone.utc


def money(v) -> str | None:
    if v in (None, ""):
        return None
    v = float(v)
    if v >= 1e7:
        return f"₹{v / 1e7:.2f}".rstrip("0").rstrip(".") + " Cr"
    if v >= 1e5:
        return f"₹{v / 1e5:.2f}".rstrip("0").rstrip(".") + " L"
    return f"₹{v:,.0f}"


def parse_when(v) -> dt.datetime | None:
    """ISO from the model; a time without an offset is the workspace's local time."""
    if v in (None, ""):
        return None
    if isinstance(v, dt.datetime):
        d = v
    else:
        s = str(v).strip().replace("Z", "+00:00")
        try:
            d = dt.datetime.fromisoformat(s)
        except ValueError:
            try:
                d = dt.datetime.combine(dt.date.fromisoformat(s[:10]), dt.time(11, 0))
            except ValueError:
                raise ActionError(f"I couldn't read the date “{v}”. Use a format like 2026-10-18T11:00.")
    if d.tzinfo is None:
        d = d.replace(tzinfo=_tz())
    return d.astimezone(dt.timezone.utc)


def when_label(d: dt.datetime | str | None) -> str | None:
    if not d:
        return None
    if isinstance(d, str):
        d = parse_when(d)
    return d.astimezone(_tz()).strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float, decimal.Decimal)):
        return float(v)
    from app.services.ai import extract

    vals = extract.money_values(str(v))
    if vals:
        return vals[0]
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        raise ActionError(f"“{v}” isn't an amount I understand. Try 85 lakh or 1.2 crore.")


def _jsonable(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, dt.datetime):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def change(key: str, label: str, before, after, *, input: str = "text", display_from=None, display_to=None, options=None) -> dict:
    return {"key": key, "label": label, "from": _jsonable(before), "to": _jsonable(after), "input": input, "options": options,
            "display_from": display_from if display_from is not None else _jsonable(before), "display_to": display_to if display_to is not None else _jsonable(after)}


# ---- lookups --------------------------------------------------------------------------------------------------------------

def _uuid(v) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(v))
    except (ValueError, TypeError):
        return None


def _candidates(rows, fmt) -> str:
    return "; ".join(fmt(r) for r in rows[:6])


def find_lead(ref) -> Lead:
    if isinstance(ref, dict):
        ref = ref.get("id") or ref.get("name")
    if not ref:
        raise ActionError("Which lead? Give me a name, phone number or open the lead first.")
    base = db.session.query(Lead).filter(Lead.workspace_id == g.workspace.id, Lead.deleted_at.is_(None))
    rid = _uuid(ref)
    if rid:
        lead = base.filter(Lead.id == rid).first()
        if lead:
            return lead
        raise ActionError("That lead doesn't exist or was deleted.")
    s = str(ref).strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 7:
        rows = base.filter(func.regexp_replace(func.coalesce(Lead.phone, ""), r"\D", "", "g").like(f"%{digits[-10:]}")).limit(5).all()
    elif "@" in s:
        rows = base.filter(func.lower(Lead.email) == s.lower()).limit(5).all()
    else:
        full = func.lower(func.concat(Lead.first_name, " ", func.coalesce(Lead.last_name, "")))
        rows = base.filter(full == s.lower()).limit(6).all() or base.filter(full.like(f"%{s.lower()}%")).order_by(Lead.updated_at.desc()).limit(6).all()
    if not rows:
        raise ActionError(f"I couldn't find a lead called “{s}”.")
    if len(rows) > 1:
        raise ActionError(f"Several leads match “{s}”: " + _candidates(rows, lambda l: f"{l.name} ({l.phone or l.email or 'no contact'}, id {l.id})") + ". Ask which one.")
    return rows[0]


def find_member(ref) -> User:
    if not ref:
        raise ActionError("Who should it be assigned to?")
    if str(ref).lower() in ("me", "myself", "mine"):
        return g.user
    q = db.session.query(User).join(WorkspaceMember, WorkspaceMember.user_id == User.id).filter(WorkspaceMember.workspace_id == g.workspace.id, WorkspaceMember.status == "active")
    rid = _uuid(ref)
    if rid:
        u = q.filter(User.id == rid).first()
    else:
        s = str(ref).strip().lower()
        rows = q.filter(or_(func.lower(User.name) == s, func.lower(User.email) == s)).all() or q.filter(func.lower(User.name).like(f"%{s}%")).all()
        if len(rows) > 1:
            raise ActionError(f"More than one teammate matches “{ref}”: " + ", ".join(u.name for u in rows[:6]) + ". Ask which one.")
        u = rows[0] if rows else None
    if not u:
        raise ActionError(f"“{ref}” isn't an active member of this workspace.")
    return u


def find_project(ref) -> Project:
    base = db.session.query(Project).filter(Project.workspace_id == g.workspace.id, Project.deleted_at.is_(None))
    rid = _uuid(ref)
    if rid:
        p = base.filter(Project.id == rid).first()
    else:
        s = str(ref or "").strip().lower()
        rows = base.filter(func.lower(Project.name) == s).all() or base.filter(func.lower(Project.name).like(f"%{s}%")).all()
        if len(rows) > 1:
            raise ActionError("Several projects match: " + ", ".join(p.name for p in rows[:6]) + ". Ask which one.")
        p = rows[0] if rows else None
    if not p:
        raise ActionError(f"I couldn't find the project “{ref}”.")
    return p


def find_unit(ref, project=None, tower=None) -> Unit:
    """A flat by id, or by number within a project (and tower), e.g. project='Green Valley', tower='B', number='1204'."""
    base = db.session.query(Unit).filter(Unit.workspace_id == g.workspace.id, Unit.deleted_at.is_(None))
    if isinstance(ref, dict):
        project, tower, ref = ref.get("project") or project, ref.get("tower") or tower, ref.get("id") or ref.get("number")
    rid = _uuid(ref)
    if rid:
        u = base.filter(Unit.id == rid).first()
        if not u:
            raise ActionError("That flat doesn't exist.")
        return u
    s = str(ref or "").strip()
    m = re.match(r"(?:(.+?)\s+)?(?:tower\s*)?([A-Za-z0-9]+)?[\s-]*?(\d{3,4})$", s, re.I)
    number = m.group(3) if m else s
    if m and not tower and m.group(2) and not m.group(2).isdigit():
        tower = m.group(2)
    q = base.filter(Unit.number == number)
    if project:
        q = q.filter(Unit.project_id == find_project(project).id)
    elif m and m.group(1):
        try:
            q = q.filter(Unit.project_id == find_project(m.group(1)).id)
        except ActionError:
            pass
    if tower:
        q = q.join(Tower, Tower.id == Unit.tower_id).filter(or_(func.lower(Tower.name) == str(tower).lower(), func.lower(Tower.name) == f"tower {str(tower).lower()}"))
    rows = q.limit(6).all()
    if not rows:
        raise ActionError(f"I couldn't find flat “{s}”. Tell me the project (and tower) too.")
    if len(rows) > 1:
        raise ActionError("Several flats match: " + ", ".join(f"{unit_label(u)} (id {u.id})" for u in rows) + ". Ask which project or tower.")
    return rows[0]


def unit_label(u: Unit) -> str:
    return inventory.labels_for({u.id}, set())[0].get(u.id) or u.name


def status_key(v: str) -> str:
    statuses = (g.workspace.settings or {}).get("lead_statuses", [])
    s = str(v).strip().lower().replace("-", " ")
    for st in statuses:
        if s in (st["key"], st["key"].replace("_", " "), st["label"].lower()):
            return st["key"]
    aliases = {"interested": "qualified", "not interested": "unqualified", "hot": "qualified", "called": "contacted", "client": "converted", "dead": "lost", "junk": "unqualified"}
    if aliases.get(s) and any(st["key"] == aliases[s] for st in statuses):
        return aliases[s]
    raise ActionError(f"“{v}” isn't a lead status here. Options: " + ", ".join(st["label"] for st in statuses if st["key"] != "converted") + ".")


def status_label(key: str | None) -> str | None:
    for st in (g.workspace.settings or {}).get("lead_statuses", []):
        if st["key"] == key:
            return st["label"]
    return key


def _status_options() -> list[list[str]]:
    return [[s["key"], s["label"]] for s in (g.workspace.settings or {}).get("lead_statuses", []) if s["key"] != "converted"]


def _member_options() -> list[list[str]]:
    rows = db.session.query(User.id, User.name).join(WorkspaceMember, WorkspaceMember.user_id == User.id).filter(
        WorkspaceMember.workspace_id == g.workspace.id, WorkspaceMember.status == "active").order_by(User.name).all()
    return [[str(i), n] for i, n in rows]


def _user_name(uid) -> str | None:
    if not uid:
        return None
    u = db.session.get(User, uid)
    return u.name if u else None


def lead_ref(lead: Lead) -> dict:
    return {"type": "lead", "id": str(lead.id), "name": lead.name, "url": f"/app/leads/{lead.id}"}


def record_ref(record) -> tuple[str, Any]:
    """{'type': 'lead'|'contact'|'deal', 'id'|'name'} -> (fk field, row)."""
    if not record:
        return "", None
    if isinstance(record, str):
        record = {"type": "lead", "name": record}
    t = record.get("type", "lead")
    if t == "lead":
        return "lead_id", find_lead(record)
    model = {"contact": Contact, "deal": Deal}.get(t)
    if not model:
        raise ActionError("I can attach this to a lead, client or deal.")
    rid = _uuid(record.get("id"))
    q = db.session.query(model).filter(model.workspace_id == g.workspace.id, model.deleted_at.is_(None))
    row = q.filter(model.id == rid).first() if rid else None
    if row is None and record.get("name"):
        col = model.name if model is Deal else func.concat(Contact.first_name, " ", func.coalesce(Contact.last_name, ""))
        rows = q.filter(func.lower(col).like(f"%{str(record['name']).lower()}%")).limit(6).all()
        if len(rows) > 1:
            raise ActionError("Several records match: " + ", ".join(r.name for r in rows) + ". Ask which one.")
        row = rows[0] if rows else None
    if row is None:
        raise ActionError(f"I couldn't find that {t}.")
    return f"{t}_id", row


def _url(fk: str, row) -> str:
    return f"/app/{ {'lead_id': 'leads', 'contact_id': 'contacts', 'deal_id': 'deals'}[fk] }/{row.id}"


# ---- lead changes -----------------------------------------------------------------------------------------------------------

def _lead_changes(lead: Lead | None, changes: dict) -> tuple[list[dict], dict, dict]:
    """(change rows, PATCH/POST body with placeholders, undo body)."""
    rows, body, undo = [], {}, {}

    def put(key, api_key, before, after, input_="text", dfrom=None, dto=None, options=None):
        if _jsonable(before) == _jsonable(after):
            return
        rows.append(change(key, LEAD_FIELDS.get(key, (key, ""))[0], before, after, input=input_, display_from=dfrom, display_to=dto, options=options))
        body[api_key] = "{{" + key + "}}"
        undo[api_key] = _jsonable(before)

    g_ = (lambda f: getattr(lead, f) if lead is not None else None)
    for k, v in (changes or {}).items():
        if v is None and k not in ("next_follow_up_at", "budget_min", "budget_max", "unit", "project"):
            continue
        if k == "status":
            key = status_key(v)
            if key == "converted":
                raise ActionError("To convert a lead into a client, use propose_convert_lead.")
            put("status", "status", g_("status"), key, "select", status_label(g_("status")), status_label(key), _status_options())
        elif k in ("owner", "owner_id", "assign_to"):
            u = find_member(v)
            put("owner", "owner_id", str(g_("owner_id")) if g_("owner_id") else None, str(u.id), "select", _user_name(g_("owner_id")), u.name, _member_options())
        elif k in ("budget_min", "budget_max"):
            n = _num(v)
            put(k, k, g_(k), n, "money", money(g_(k)), money(n))
        elif k == "next_follow_up_at":
            d = parse_when(v)
            put(k, k, g_(k), d, "datetime", when_label(g_(k)), when_label(d))
        elif k == "intent":
            if v not in [i[0] for i in INTENTS]:
                raise ActionError("Looking to must be buy, rent, invest, sell or lease.")
            put(k, k, g_(k), v, "select", options=INTENTS)
        elif k == "property_type":
            if v not in [i[0] for i in PROPERTY_TYPES]:
                raise ActionError("Property type must be apartment, villa, plot, office, shop or other.")
            put(k, k, g_(k), v, "select", options=PROPERTY_TYPES)
        elif k == "bhk":
            from app.services.ai import extract

            put(k, k, g_(k), extract.bhk(str(v)) or str(v)[:20])
        elif k in ("add_tags", "remove_tags", "tags"):
            cur = list(g_("tags") or [])
            vals = [str(t).strip()[:40] for t in (v if isinstance(v, list) else str(v).split(",")) if str(t).strip()]
            new = sorted(set(cur) | set(vals)) if k == "add_tags" else [t for t in cur if t not in vals] if k == "remove_tags" else vals
            put("tags", "tags", cur, new, "tags", ", ".join(cur) or None, ", ".join(new) or None)
        elif k == "project":
            p = find_project(v) if v else None
            put("project", "project_id", str(g_("project_id")) if g_("project_id") else None, str(p.id) if p else None, "readonly",
                db.session.get(Project, g_("project_id")).name if g_("project_id") else None, p.name if p else None)
        elif k == "unit":
            u = find_unit(v) if v else None
            put("unit", "unit_id", str(g_("unit_id")) if g_("unit_id") else None, str(u.id) if u else None, "readonly",
                unit_label(db.session.get(Unit, g_("unit_id"))) if g_("unit_id") else None, unit_label(u) if u else None)
        elif k == "phone":
            from app.services.ai import extract

            put(k, k, g_(k), extract.normalize_phone(str(v)))
        elif k in ("first_name", "last_name", "email", "location", "source", "description", "company_name", "lost_reason"):
            put(k, k, g_(k), str(v).strip() or None, "textarea" if k == "description" else "text")
        elif k == "name":
            first, *rest = str(v).split()
            put("first_name", "first_name", g_("first_name"), first)
            put("last_name", "last_name", g_("last_name"), " ".join(rest) or None)
    return rows, body, undo


def propose_update_lead(lead: str | dict, changes: dict, reason: str | None = None) -> dict:
    _need("leads.update", "edit leads")
    l = find_lead(lead)
    if l.status == "converted" and "status" in (changes or {}):
        raise ActionError("This lead has already become a client; its status can't change.")
    rows, body, undo = _lead_changes(l, changes)
    if not rows:
        raise ActionError("Nothing would change: the lead already has those values.")
    return _add(proposal("update_lead", f"Update {l.name}", record=lead_ref(l), changes=rows, description=reason,
                         ops=[{"method": "PATCH", "path": f"/api/v1/leads/{l.id}", "body": body}],
                         undo=[{"method": "PATCH", "path": f"/api/v1/leads/{l.id}", "body": undo}]))


def propose_create_lead(fields: dict, reason: str | None = None, duplicates: list[dict] | None = None) -> dict:
    _need("leads.create", "create leads")
    fields = dict(fields or {})
    if not (fields.get("first_name") or fields.get("name")):
        fields["first_name"] = fields.get("phone") or "New enquiry"
    rows, body, _ = _lead_changes(None, fields)
    p = proposal("create_lead", f"New lead: {' '.join(x for x in (fields.get('first_name') or fields.get('name'), fields.get('last_name')) if x)}", changes=rows,
                 description=reason, ops=[{"method": "POST", "path": "/api/v1/leads", "body": body}],
                 undo=[{"method": "DELETE", "path": "/api/v1/leads/{{result.0.id}}"}],
                 warning=("Possible duplicate: " + "; ".join(f"{d['name']} ({d.get('phone') or d.get('email') or ''})" for d in duplicates[:3])) if duplicates else None,
                 extra={"duplicates": duplicates or [], "open_result": "/app/leads/{{result.0.id}}"})
    return _add(p)


def propose_convert_lead(lead: str | dict, create_deal: bool = True, deal_value: float | str | None = None) -> dict:
    _need("leads.convert", "convert leads")
    l = find_lead(lead)
    if l.converted_at:
        raise ActionError("This lead is already a client.")
    body: dict = {"create_company": bool(l.company_name), "create_deal": bool(create_deal)}
    rows = [change("convert", "Becomes", status_label(l.status), "Client" + (" + deal" if create_deal else ""), input="readonly")]
    if create_deal and deal_value not in (None, ""):
        n = _num(deal_value)
        body["deal_value"] = "{{deal_value}}"
        rows.append(change("deal_value", "Deal value", None, n, input="money", display_to=money(n)))
    return _add(proposal("convert_lead", f"Convert {l.name} into a client", record=lead_ref(l), changes=rows,
                         ops=[{"method": "POST", "path": f"/api/v1/leads/{l.id}/convert", "body": body}],
                         warning="Converting can't be undone automatically.", extra={"open_result": "/app/contacts/{{result.0.contact_id}}"}))


def _lead_query(f: dict):
    q = db.session.query(Lead).filter(Lead.workspace_id == g.workspace.id, Lead.deleted_at.is_(None))
    if f.get("source"):
        q = q.filter(func.lower(Lead.source) == str(f["source"]).lower())
    if f.get("status"):
        q = q.filter(Lead.status == status_key(f["status"]))
    elif not f.get("include_closed"):
        q = q.filter(Lead.status.notin_(("converted", "lost", "unqualified")))
    if f.get("owner"):
        q = q.filter(Lead.owner_id == find_member(f["owner"]).id) if str(f["owner"]).lower() not in ("none", "unassigned") else q.filter(Lead.owner_id.is_(None))
    if f.get("created_within_days"):
        q = q.filter(Lead.created_at >= utcnow() - dt.timedelta(days=int(f["created_within_days"])))
    if f.get("stale_days"):
        cut = utcnow() - dt.timedelta(days=int(f["stale_days"]))
        q = q.filter(or_(Lead.last_contacted_at.is_(None), Lead.last_contacted_at < cut))
    if f.get("min_budget") not in (None, ""):
        q = q.filter(Lead.budget_max >= _num(f["min_budget"]))
    if f.get("max_budget") not in (None, ""):
        q = q.filter(or_(Lead.budget_min.is_(None), Lead.budget_min <= _num(f["max_budget"])))
    if f.get("bhk"):
        from app.services.ai import extract

        q = q.filter(Lead.bhk == (extract.bhk(str(f["bhk"])) or f["bhk"]))
    if f.get("intent"):
        q = q.filter(Lead.intent == f["intent"])
    if f.get("location"):
        q = q.filter(Lead.location.ilike(f"%{f['location']}%"))
    if f.get("project"):
        q = q.filter(Lead.project_id == find_project(f["project"]).id)
    if f.get("tag"):
        q = q.filter(Lead.tags.any(str(f["tag"])))
    if f.get("min_score"):
        q = q.filter(Lead.score >= int(f["min_score"]))
    return q


def propose_bulk_update_leads(filter: dict, changes: dict, description: str | None = None) -> dict:
    _need("leads.update", "edit leads")
    leads = _lead_query(filter or {}).order_by(Lead.created_at.desc()).limit(MAX_BULK + 1).all()
    if not leads:
        raise ActionError("No leads match those conditions, so nothing would change.")
    if len(leads) > MAX_BULK:
        raise ActionError(f"More than {MAX_BULK} leads match. Narrow it down (for example by source, date or owner).")
    ids = [str(l.id) for l in leads]
    ops, undo, rows = [], [], []
    for k, v in (changes or {}).items():
        if k in ("owner", "owner_id", "assign_to"):
            u = find_member(v)
            rows.append(change("owner", "Owner", None, str(u.id), input="select", display_from="(various)", display_to=u.name, options=_member_options()))
            ops.append({"method": "POST", "path": "/api/v1/leads/bulk", "body": {"ids": ids, "action": "assign", "value": "{{owner}}"}})
            undo += [{"method": "PATCH", "path": f"/api/v1/leads/{l.id}", "body": {"owner_id": str(l.owner_id) if l.owner_id else None}} for l in leads]
        elif k == "status":
            key = status_key(v)
            rows.append(change("status", "Status", None, key, input="select", display_from="(various)", display_to=status_label(key), options=_status_options()))
            ops.append({"method": "POST", "path": "/api/v1/leads/bulk", "body": {"ids": ids, "action": "set", "value": {"status": "{{status}}"}}})
            undo += [{"method": "PATCH", "path": f"/api/v1/leads/{l.id}", "body": {"status": l.status}} for l in leads]
        elif k in ("add_tags", "remove_tags"):
            vals = [str(t).strip()[:40] for t in (v if isinstance(v, list) else str(v).split(",")) if str(t).strip()]
            rows.append(change(k, "Add tags" if k == "add_tags" else "Remove tags", None, ", ".join(vals), input="readonly"))
            ops.append({"method": "POST", "path": "/api/v1/leads/bulk", "body": {"ids": ids, "action": k, "value": vals}})
            undo.append({"method": "POST", "path": "/api/v1/leads/bulk", "body": {"ids": ids, "action": "remove_tags" if k == "add_tags" else "add_tags", "value": vals}})
        elif k == "next_follow_up_at":
            d = parse_when(v)
            rows.append(change(k, "Follow-up", None, d, input="datetime", display_from="(various)", display_to=when_label(d)))
            ops += [{"method": "PATCH", "path": f"/api/v1/leads/{l.id}", "body": {"next_follow_up_at": "{{next_follow_up_at}}"}} for l in leads]
            undo += [{"method": "PATCH", "path": f"/api/v1/leads/{l.id}", "body": {"next_follow_up_at": _jsonable(l.next_follow_up_at)}} for l in leads]
    if not ops:
        raise ActionError("Bulk changes can set the owner, status, follow-up date or tags.")
    items = [{"id": str(l.id), "name": l.name, "url": f"/app/leads/{l.id}", "hint": " · ".join(x for x in (l.source, money(l.budget_max), l.bhk) if x)} for l in leads]
    return _add(proposal("bulk_update_leads", f"Update {len(leads)} lead{'s' if len(leads) != 1 else ''}", changes=rows, ops=ops, undo=undo, items=items, description=description))


# ---- activities -------------------------------------------------------------------------------------------------------------

def propose_create_task(title: str, due_at: str | None = None, priority: str = "medium", record: dict | str | None = None, assignee: str | None = None,
                        description: str | None = None) -> dict:
    _need("tasks.create", "create tasks")
    if not title or not str(title).strip():
        raise ActionError("What should the task say?")
    fk, row = record_ref(record)
    due = parse_when(due_at)
    who = find_member(assignee) if assignee else g.user
    pr = priority if priority in ("low", "medium", "high", "urgent") else "medium"
    body = {"title": "{{title}}", "due_at": "{{due_at}}", "priority": "{{priority}}", "assignee_id": "{{assignee}}", "kind": "follow_up" if fk else "task",
            "description": description}
    if fk:
        body[fk] = str(row.id)
    rows = [change("title", "Task", None, str(title).strip()[:240]), change("due_at", "Due", None, due, input="datetime", display_to=when_label(due) or "No date"),
            change("priority", "Priority", None, pr, input="select", options=[["low", "Low"], ["medium", "Medium"], ["high", "High"], ["urgent", "Urgent"]]),
            change("assignee", "For", None, str(who.id), input="select", display_to=who.name, options=_member_options())]
    return _add(proposal("create_task", f"New task{' for ' + row.name if row is not None else ''}", changes=rows,
                         record={"type": fk[:-3], "id": str(row.id), "name": row.name, "url": _url(fk, row)} if fk else None,
                         ops=[{"method": "POST", "path": "/api/v1/tasks", "body": body}], undo=[{"method": "DELETE", "path": "/api/v1/tasks/{{result.0.id}}"}]))


def propose_log_note(record: dict | str, body: str) -> dict:
    _need("notes.create", "add notes")
    fk, row = record_ref(record)
    if not row:
        raise ActionError("Which lead or client is the note for?")
    return _add(proposal("log_note", f"Add a note to {row.name}", record={"type": fk[:-3], "id": str(row.id), "name": row.name, "url": _url(fk, row)},
                         changes=[change("body", "Note", None, str(body).strip(), input="textarea")],
                         ops=[{"method": "POST", "path": "/api/v1/notes", "body": {"body": "{{body}}", fk: str(row.id)}}],
                         undo=[{"method": "DELETE", "path": "/api/v1/notes/{{result.0.id}}"}]))


CALL_OUTCOMES = [["connected", "Connected"], ["no_answer", "No answer"], ["follow_up_required", "Follow-up needed"], ["interested", "Interested"], ["not_interested", "Not interested"]]


def propose_log_call(record: dict | str, outcome: str | None = None, notes: str | None = None, direction: str = "outbound", occurred_at: str | None = None,
                     duration_minutes: int | None = None) -> dict:
    _need("meetings.create", "log calls")
    fk, row = record_ref(record)
    if not row:
        raise ActionError("Who was the call with?")
    when = parse_when(occurred_at) or utcnow()
    oc = outcome if outcome in [o[0] for o in CALL_OUTCOMES] else None
    body = {"direction": direction if direction in ("inbound", "outbound") else "outbound", "status": "completed", "outcome": "{{outcome}}", "notes": "{{notes}}",
            "occurred_at": "{{occurred_at}}", "phone": getattr(row, "phone", None), fk: str(row.id),
            "duration_seconds": int(duration_minutes) * 60 if duration_minutes else None}
    rows = [change("outcome", "Outcome", None, oc, input="select", options=CALL_OUTCOMES, display_to=dict(CALL_OUTCOMES).get(oc or "", "—")),
            change("notes", "Notes", None, notes or "", input="textarea"), change("occurred_at", "When", None, when, input="datetime", display_to=when_label(when))]
    return _add(proposal("log_call", f"Log a call with {row.name}", record={"type": fk[:-3], "id": str(row.id), "name": row.name, "url": _url(fk, row)}, changes=rows,
                         ops=[{"method": "POST", "path": "/api/v1/calls", "body": body}], undo=[{"method": "DELETE", "path": "/api/v1/calls/{{result.0.id}}"}]))


def visit_op(lead: Lead, starts: dt.datetime, minutes: int, project: Project | None, unit: Unit | None, status: str, notes: str | None, location: str | None) -> tuple[list[dict], dict]:
    title = f"Site visit: {lead.name}" + (f" at {project.name}" if project else "")
    body = {"title": "{{visit_title}}", "kind": "site_visit", "starts_at": "{{starts_at}}", "ends_at": (starts + dt.timedelta(minutes=minutes)).isoformat(), "status": status,
            "lead_id": str(lead.id), "project_id": str(project.id) if project else None, "unit_id": str(unit.id) if unit else None,
            "location": location or (project.address or project.locality if project else None), "description": notes, "summary": notes if status == "completed" else None,
            "attendees": [{"name": lead.name, "email": lead.email}] if lead.email else []}
    rows = [change("visit_title", "Visit", None, title), change("starts_at", "When", None, starts, input="datetime", display_to=when_label(starts))]
    if project:
        rows.append(change("visit_project", "Project", None, project.name, input="readonly"))
    if unit:
        rows.append(change("visit_unit", "Flat", None, unit_label(unit), input="readonly"))
    return rows, body


def propose_schedule_visit(lead: str | dict, starts_at: str, duration_minutes: int = 60, project: str | None = None, unit: str | dict | None = None,
                           location: str | None = None, notes: str | None = None) -> dict:
    _need("meetings.create", "schedule site visits")
    l = find_lead(lead)
    starts = parse_when(starts_at)
    if not starts:
        raise ActionError("When is the site visit?")
    u = find_unit(unit, project) if unit else None
    p = find_project(project) if project else (db.session.get(Project, u.project_id) if u else (db.session.get(Project, l.project_id) if l.project_id else None))
    rows, body = visit_op(l, starts, int(duration_minutes or 60), p, u, "scheduled", notes, location)
    return _add(proposal("schedule_visit", f"Schedule a site visit with {l.name}", record=lead_ref(l), changes=rows,
                         ops=[{"method": "POST", "path": "/api/v1/meetings", "body": body}], undo=[{"method": "DELETE", "path": "/api/v1/meetings/{{result.0.id}}"}]))


# ---- inventory -----------------------------------------------------------------------------------------------------------

def propose_update_unit(unit: str | dict, status: str | None = None, hold_hours: int | None = None, lead: str | dict | None = None, project: str | None = None,
                        sale_price: float | str | None = None, monthly_rent: float | str | None = None, note: str | None = None) -> dict:
    _need("units.update", "change flats")
    u = find_unit(unit, project)
    rows, ops, undo = [], [], []
    if status:
        st = str(status).lower().replace(" ", "_").replace("hold", "on_hold").replace("on_on_hold", "on_hold")
        if st not in inventory.STATUSES:
            raise ActionError("Flat status must be one of: " + ", ".join(v["label"] for v in inventory.STATUSES.values()) + ".")
        l = find_lead(lead) if lead else None
        body: dict = {"status": "{{unit_status}}", "note": note}
        if st == "on_hold":
            body["hold_hours"] = "{{hold_hours}}"
        if l:
            body["lead_id"] = str(l.id)
        rows.append(change("unit_status", "Status", u.status, st, input="select", display_from=inventory.STATUSES[u.status]["label"], display_to=inventory.STATUSES[st]["label"],
                           options=[[k, v["label"]] for k, v in inventory.STATUSES.items()]))
        if st == "on_hold":
            h = int(hold_hours or inventory.DEFAULT_HOLD_HOURS)
            rows.append(change("hold_hours", "Hold for (hours)", None, h, input="number"))
        if l:
            rows.append(change("unit_lead", "For", None, l.name, input="readonly"))
        ops.append({"method": "POST", "path": f"/api/v1/units/{u.id}/status", "body": body})
        undo.append({"method": "POST", "path": f"/api/v1/units/{u.id}/status", "body": {"status": u.status, "note": "Undone"}})
    price: dict = {}
    for k, v in (("sale_price", sale_price), ("monthly_rent", monthly_rent)):
        if v not in (None, ""):
            n = _num(v)
            rows.append(change(k, "Sale price" if k == "sale_price" else "Monthly rent", getattr(u, k), n, input="money", display_from=money(getattr(u, k)), display_to=money(n)))
            price[k] = "{{" + k + "}}"
    if price:
        ops.append({"method": "PATCH", "path": f"/api/v1/units/{u.id}", "body": price})
        undo.append({"method": "PATCH", "path": f"/api/v1/units/{u.id}", "body": {k: _jsonable(getattr(u, k)) for k in price}})
    if not ops:
        raise ActionError("What should change on the flat: status, hold, or price?")
    return _add(proposal("update_unit", f"Update flat {unit_label(u)}", changes=rows, ops=ops, undo=undo,
                         record={"type": "unit", "id": str(u.id), "name": unit_label(u), "url": f"/app/projects/{u.project_id}?tower={u.tower_id}&unit={u.id}"}))


# ---- promises to buyers ------------------------------------------------------------------------------------------------------

PROMISE_KINDS = [["discount", "Discount"], ["parking", "Parking"], ["fittings", "Fittings & furnishing"], ["possession", "Possession date"],
                 ["payment_plan", "Payment plan"], ["waiver", "Charge waived"], ["other", "Other"]]


def propose_record_promise(record: dict | str, title: str, kind: str = "other", details: str | None = None, value: float | str | None = None,
                           promised_by: str | None = None, source: str = "chat", quote: str | None = None, promised_on: str | None = None) -> dict:
    """A promise a rep made to a buyer. Approving the card records it as waiting for a manager; it isn't approved yet."""
    _need("promises.create", "record promises")
    fk, row = record_ref(record)
    if not row:
        raise ActionError("Which buyer was the promise made to?")
    title = str(title or "").strip()[:200]
    if len(title) < 2:
        raise ActionError("What was promised?")
    who = find_member(promised_by) if promised_by else g.user
    k = kind if kind in dict(PROMISE_KINDS) else "other"
    v = _num(value)
    rows = [change("title", "Promise", None, title), change("kind", "Type", None, k, input="select", options=PROMISE_KINDS, display_to=dict(PROMISE_KINDS)[k]),
            change("value", "Worth", None, v, input="money", display_to=money(v) or "—"),
            change("promised_by", "Promised by", None, str(who.id), input="select", options=_member_options(), display_to=who.name),
            change("details", "Details", None, (details or "").strip()[:4000], input="textarea")]
    if quote:
        rows.append(change("quote", "Picked up from", None, f"“{str(quote).strip()[:400]}”", input="readonly"))
    body = {fk: str(row.id), "title": "{{title}}", "kind": "{{kind}}", "value": "{{value}}", "promised_by": "{{promised_by}}", "details": "{{details}}",
            "source": source if source in ("whatsapp", "call", "visit", "note", "chat") else "chat", "source_text": (str(quote).strip()[:2000] if quote else None),
            "promised_on": str(promised_on)[:10] if promised_on else None}
    return _add(proposal("record_promise", f"Record promise: {title}", record={"type": fk[:-3], "id": str(row.id), "name": row.name, "url": _url(fk, row)},
                         changes=rows, description=f"{who.name} promised this to {row.name}. Once saved, a manager approves or rejects it.",
                         ops=[{"method": "POST", "path": "/api/v1/promises", "body": body}],
                         undo=[{"method": "POST", "path": "/api/v1/promises/{{result.0.id}}/cancel", "body": {"note": "Undone right after recording"}}]))


def propose_navigation(url: str, label: str, explanation: str | None = None) -> dict:
    if not str(url).startswith("/app"):
        raise ActionError("I can only open pages inside CRM Wala.")
    return _add(proposal("navigate", label, ops=[], url=url, description=explanation))


PROPOSERS = {
    "propose_update_lead": propose_update_lead, "propose_create_lead": propose_create_lead, "propose_convert_lead": propose_convert_lead,
    "propose_bulk_update_leads": propose_bulk_update_leads, "propose_create_task": propose_create_task, "propose_log_note": propose_log_note,
    "propose_log_call": propose_log_call, "propose_schedule_visit": propose_schedule_visit, "propose_update_unit": propose_update_unit,
    "propose_record_promise": propose_record_promise, "propose_navigation": propose_navigation,
}

_REF = {"type": "object", "description": "The record: {type: lead|contact|deal, id or name}", "properties": {"type": {"type": "string", "enum": ["lead", "contact", "deal"]},
                                                                                                         "id": {"type": "string"}, "name": {"type": "string"}}}
_LEAD = {"type": "string", "description": "Lead id (preferred), full name, phone or email"}
_WHEN = {"type": "string", "description": "ISO date-time in the workspace's local time, e.g. 2026-10-18T11:00"}
LEAD_CHANGE_PROPS = {
    "status": {"type": "string", "description": "Lead status key or label"}, "owner": {"type": "string", "description": "Teammate name, email or 'me'"},
    "budget_min": {"type": "number", "description": "Rupees, e.g. 8500000 for 85 lakh"}, "budget_max": {"type": "number", "description": "Rupees"},
    "bhk": {"type": "string", "description": "e.g. '3 BHK'"}, "intent": {"type": "string", "enum": [i[0] for i in INTENTS]},
    "property_type": {"type": "string", "enum": [i[0] for i in PROPERTY_TYPES]}, "location": {"type": "string", "description": "Preferred area"},
    "next_follow_up_at": _WHEN, "source": {"type": "string"}, "phone": {"type": "string"}, "email": {"type": "string"}, "first_name": {"type": "string"},
    "last_name": {"type": "string"}, "description": {"type": "string", "description": "Replaces the lead's notes field"}, "add_tags": {"type": "array", "items": {"type": "string"}},
    "remove_tags": {"type": "array", "items": {"type": "string"}}, "project": {"type": "string", "description": "Project name the lead is interested in"},
    "unit": {"type": "string", "description": "Flat id or 'Project Tower 1204'"}, "lost_reason": {"type": "string"},
}
SPECS: list[dict] = [
    {"name": "propose_update_lead", "description": "Prepare changes to one lead (status, owner, budget, BHK, follow-up, tags, notes…). The user approves before it's saved.",
     "input_schema": {"type": "object", "properties": {"lead": _LEAD, "changes": {"type": "object", "properties": LEAD_CHANGE_PROPS}, "reason": {"type": "string"}},
                      "required": ["lead", "changes"]}},
    {"name": "propose_create_lead", "description": "Prepare a new lead from details the user gave.",
     "input_schema": {"type": "object", "properties": {"fields": {"type": "object", "properties": LEAD_CHANGE_PROPS}, "reason": {"type": "string"}}, "required": ["fields"]}},
    {"name": "propose_convert_lead", "description": "Prepare converting a lead into a client (and optionally a deal).",
     "input_schema": {"type": "object", "properties": {"lead": _LEAD, "create_deal": {"type": "boolean"}, "deal_value": {"type": "number"}}, "required": ["lead"]}},
    {"name": "propose_bulk_update_leads", "description": "Prepare the same change to many leads that match conditions (max 200). Shows the list for approval.",
     "input_schema": {"type": "object", "properties": {
         "filter": {"type": "object", "properties": {"source": {"type": "string"}, "status": {"type": "string"}, "owner": {"type": "string", "description": "name, 'me' or 'unassigned'"},
                                                     "created_within_days": {"type": "integer"}, "stale_days": {"type": "integer", "description": "Not contacted for N days"},
                                                     "min_budget": {"type": "number"}, "max_budget": {"type": "number"}, "bhk": {"type": "string"}, "intent": {"type": "string"},
                                                     "location": {"type": "string"}, "project": {"type": "string"}, "tag": {"type": "string"}, "min_score": {"type": "integer"}}},
         "changes": {"type": "object", "properties": {"owner": {"type": "string"}, "status": {"type": "string"}, "next_follow_up_at": _WHEN,
                                                      "add_tags": {"type": "array", "items": {"type": "string"}}, "remove_tags": {"type": "array", "items": {"type": "string"}}}},
         "description": {"type": "string"}}, "required": ["filter", "changes"]}},
    {"name": "propose_create_task", "description": "Prepare a task or reminder, optionally linked to a lead, client or deal.",
     "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "due_at": _WHEN, "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                                                       "record": _REF, "assignee": {"type": "string"}, "description": {"type": "string"}}, "required": ["title"]}},
    {"name": "propose_log_note", "description": "Prepare a note on a lead, client or deal.",
     "input_schema": {"type": "object", "properties": {"record": _REF, "body": {"type": "string"}}, "required": ["record", "body"]}},
    {"name": "propose_log_call", "description": "Prepare logging a phone call that happened.",
     "input_schema": {"type": "object", "properties": {"record": _REF, "outcome": {"type": "string", "enum": [o[0] for o in CALL_OUTCOMES]}, "notes": {"type": "string"},
                                                       "direction": {"type": "string", "enum": ["inbound", "outbound"]}, "occurred_at": _WHEN, "duration_minutes": {"type": "integer"}},
                      "required": ["record"]}},
    {"name": "propose_schedule_visit", "description": "Prepare a site visit for a lead (optionally at a project / specific flat).",
     "input_schema": {"type": "object", "properties": {"lead": _LEAD, "starts_at": _WHEN, "duration_minutes": {"type": "integer"}, "project": {"type": "string"},
                                                       "unit": {"type": "string"}, "location": {"type": "string"}, "notes": {"type": "string"}}, "required": ["lead", "starts_at"]}},
    {"name": "propose_update_unit", "description": "Prepare a change to a flat: status (for_sale, for_rent, on_hold, booked, sold, rented, vacant, self_occupied), a hold for a lead, or price.",
     "input_schema": {"type": "object", "properties": {"unit": {"type": "string", "description": "Flat id, or number like '1204' with project/tower"}, "project": {"type": "string"},
                                                       "status": {"type": "string"}, "hold_hours": {"type": "integer"}, "lead": _LEAD, "sale_price": {"type": "number"},
                                                       "monthly_rent": {"type": "number"}, "note": {"type": "string"}}, "required": ["unit"]}},
    {"name": "propose_record_promise", "description": "Prepare recording a promise a rep made to a buyer (discount, free parking, modular kitchen, possession date, payment plan, "
                                                "waived charge). It is saved as waiting for a manager's approval. Use when the user says someone promised or offered a buyer something.",
     "input_schema": {"type": "object", "properties": {"record": _REF, "title": {"type": "string", "description": "Short, e.g. 'Free covered parking' or 'Discount of ₹2 L'"},
                                                       "kind": {"type": "string", "enum": [k[0] for k in PROMISE_KINDS]}, "details": {"type": "string"},
                                                       "value": {"type": "number", "description": "Rupees it is worth, if known"},
                                                       "promised_by": {"type": "string", "description": "Teammate who made the promise (name or 'me')"},
                                                       "quote": {"type": "string", "description": "The words it came from, if any"}}, "required": ["record", "title"]}},
    {"name": "propose_navigation", "description": "Offer a button that opens a page in CRM Wala (e.g. /app/settings/team). Use for 'take me to' / 'show me where'.",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}, "label": {"type": "string"}, "explanation": {"type": "string"}}, "required": ["url", "label"]}},
]


def run(name: str, args: dict) -> dict:
    fn = PROPOSERS[name]
    allowed = {k: v for k, v in (args or {}).items() if k in fn.__code__.co_varnames[:fn.__code__.co_argcount]}
    try:
        return fn(**allowed)
    except ActionError as e:
        return {"error": str(e)}
    except TypeError:
        return {"error": "Missing or invalid details for that change."}
