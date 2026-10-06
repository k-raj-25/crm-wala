"""CRM query tools exposed to the assistant.

Security: every tool reads `g.workspace` / `g.user` itself. The model can NEVER choose a workspace, and each tool
checks the caller's read permission, so the assistant sees exactly what the signed-in user could see.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Callable

from flask import g
from sqlalchemy import func, or_

from app.core import search_expr
from app.core.permissions import has_permission
from app.extensions import db
from app.models import Company, Contact, Deal, Lead, Task, User, WorkspaceMember
from app.models.base import utcnow
from app.services import reporting


def _can(p: str) -> bool:
    return has_permission(g.permissions, p)


def _deal_row(d: Deal) -> dict:
    return {"id": str(d.id), "name": d.name, "company": d.company.name if d.company else None, "value": float(d.value), "currency": d.currency, "stage": d.stage.name, "probability": d.probability,
            "expected_close": d.expected_close_date.isoformat() if d.expected_close_date else None, "days_since_activity": (utcnow() - d.last_activity_at).days if d.last_activity_at else None,
            "url": f"/app/deals/{d.id}"}


def _lead_row(l: Lead) -> dict:
    return {"id": str(l.id), "name": l.name, "company": l.company_name, "status": l.status, "score": l.score, "source": l.source,
            "days_since_contact": (utcnow() - l.last_contacted_at).days if l.last_contacted_at else None, "url": f"/app/leads/{l.id}"}


def list_deals(status: str = "open", closing: str | None = None, sort: str = "value", min_value: float | None = None, stale_days: int | None = None, limit: int = 8) -> dict:
    if not _can("deals.read"):
        return {"error": "You don't have permission to view deals."}
    q = db.session.query(Deal).filter(Deal.workspace_id == g.workspace.id, Deal.deleted_at.is_(None))
    if status in ("open", "won", "lost"):
        q = q.filter(Deal.status == status)
    today = utcnow().date()
    if closing == "this_month":
        start = today.replace(day=1)
        end = (start + dt.timedelta(days=32)).replace(day=1)
        q = q.filter(Deal.expected_close_date >= start, Deal.expected_close_date < end)
    elif closing == "next_30_days":
        q = q.filter(Deal.expected_close_date >= today, Deal.expected_close_date <= today + dt.timedelta(days=30))
    if min_value:
        q = q.filter(Deal.value >= min_value)
    if stale_days:
        q = q.filter(or_(Deal.last_activity_at < utcnow() - dt.timedelta(days=stale_days), Deal.last_activity_at.is_(None)))
    order = {"value": Deal.value.desc(), "probability": (Deal.probability * Deal.value).desc(), "close_date": Deal.expected_close_date.asc()}.get(sort, Deal.value.desc())
    rows = q.order_by(order).limit(min(limit, 20)).all()
    total = db.session.query(func.coalesce(func.sum(Deal.value), 0), func.count()).filter(Deal.id.in_([r.id for r in rows])).one() if rows else (0, 0)
    return {"deals": [_deal_row(r) for r in rows], "total_value": float(total[0]), "count": total[1]}


def list_leads(status: str | None = None, stale_days: int | None = None, min_score: int | None = None, source: str | None = None, limit: int = 8) -> dict:
    if not _can("leads.read"):
        return {"error": "You don't have permission to view leads."}
    q = db.session.query(Lead).filter(Lead.workspace_id == g.workspace.id, Lead.deleted_at.is_(None))
    if status:
        q = q.filter(Lead.status == status)
    else:
        q = q.filter(Lead.status.in_(("new", "contacted", "qualified")))
    if stale_days:
        q = q.filter(or_(Lead.last_contacted_at.is_(None), Lead.last_contacted_at < utcnow() - dt.timedelta(days=stale_days)))
    if min_score:
        q = q.filter(Lead.score >= min_score)
    if source:
        q = q.filter(Lead.source == source)
    total = q.count()
    rows = q.order_by(Lead.score.desc(), Lead.created_at.desc()).limit(min(limit, 20)).all()
    return {"leads": [_lead_row(r) for r in rows], "total": total}


def list_tasks(view: str = "today", mine: bool = True, limit: int = 10) -> dict:
    if not _can("tasks.read"):
        return {"error": "You don't have permission to view tasks."}
    now = utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    q = db.session.query(Task).filter(Task.workspace_id == g.workspace.id, Task.deleted_at.is_(None), Task.status != "completed")
    if mine:
        q = q.filter(Task.assignee_id == g.user.id)
    if view == "today":
        q = q.filter(Task.due_at >= start, Task.due_at < start + dt.timedelta(days=1))
    elif view == "overdue":
        q = q.filter(Task.due_at < start)
    elif view == "upcoming":
        q = q.filter(Task.due_at >= start + dt.timedelta(days=1))
    rows = q.order_by(Task.due_at).limit(limit).all()
    return {"tasks": [{"id": str(t.id), "title": t.title, "due_at": t.due_at.isoformat() if t.due_at else None, "priority": t.priority, "url": "/app/tasks"} for t in rows]}


def pipeline_summary() -> dict:
    if not _can("deals.read"):
        return {"error": "You don't have permission to view deals."}
    stages = reporting.pipeline_by_stage(g.workspace.id)
    return {"stages": stages, "open_value": sum(s["value"] for s in stages), "weighted_value": sum(s["weighted"] for s in stages), "open_deals": sum(s["deals"] for s in stages)}


def team_performance(days: int = 90) -> dict:
    if not _can("reports.read"):
        return {"error": "You don't have permission to view reports."}
    end = utcnow()
    r = reporting.run_report("team_performance", end - dt.timedelta(days=days), end)
    return {"days": days, "reps": [{k: row[k] for k in ("rep", "deals_won", "deals_lost", "win_rate", "revenue", "open_deals", "new_leads", "leads_converted")} for row in r["rows"]]}


def revenue_trend(days: int = 90) -> dict:
    if not _can("reports.read"):
        return {"error": "You don't have permission to view reports."}
    end = utcnow()
    start = end - dt.timedelta(days=days)
    m = reporting.headline_metrics(g.workspace.id, start, end)
    return {"days": days, "revenue": m["revenue"], "deals_won": m["deals_won"], "deals_lost": m["deals_lost"], "conversion_rate": m["conversion_rate"], "new_leads": m["new_leads"],
            "pipeline_value": m["pipeline_value"]}


def search_crm(query: str, limit: int = 5) -> dict:
    like = f"%{query.replace('%', '')[:80]}%"
    out: dict[str, list] = {}
    ws = g.workspace.id
    if _can("contacts.read"):
        out["contacts"] = [{"id": str(r.id), "name": r.name, "company": r.company.name if r.company else None, "url": f"/app/contacts/{r.id}"} for r in
                           db.session.query(Contact).filter(Contact.workspace_id == ws, Contact.deleted_at.is_(None), search_expr.CONTACTS.ilike(like)).limit(limit)]
    if _can("leads.read"):
        out["leads"] = [{"id": str(r.id), "name": r.name, "company": r.company_name, "url": f"/app/leads/{r.id}"} for r in
                        db.session.query(Lead).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), search_expr.LEADS.ilike(like)).limit(limit)]
    if _can("companies.read"):
        out["companies"] = [{"id": str(r.id), "name": r.name, "url": f"/app/companies/{r.id}"} for r in
                            db.session.query(Company).filter(Company.workspace_id == ws, Company.deleted_at.is_(None), search_expr.COMPANIES.ilike(like)).limit(limit)]
    if _can("deals.read"):
        out["deals"] = [{"id": str(r.id), "name": r.name, "stage": r.stage.name, "value": float(r.value), "url": f"/app/deals/{r.id}"} for r in
                        db.session.query(Deal).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), search_expr.DEALS.ilike(like)).limit(limit)]
    return {k: v for k, v in out.items() if v}


def record_context(entity: str, ident: str) -> dict:
    """Rich context about one record for summaries / drafts."""
    from app.models import Activity, Note

    model = {"lead": Lead, "contact": Contact, "company": Company, "deal": Deal}.get(entity)
    if model is None or not _can(f"{entity}s.read" if entity != "company" else "companies.read"):
        return {"error": "Not available"}
    try:
        rid = uuid.UUID(ident)
    except ValueError:
        return {"error": "Invalid id"}
    rec = db.session.query(model).filter(model.id == rid, model.workspace_id == g.workspace.id, model.deleted_at.is_(None)).first()
    if rec is None:
        return {"error": "Record not found"}
    col = getattr(Activity, f"{entity}_id")
    acts = db.session.query(Activity).filter(Activity.workspace_id == g.workspace.id, col == rid).order_by(Activity.occurred_at.desc()).limit(12).all()
    notes = db.session.query(Note).filter(Note.workspace_id == g.workspace.id, Note.deleted_at.is_(None), getattr(Note, f"{entity}_id") == rid).order_by(Note.created_at.desc()).limit(5).all()
    base: dict[str, Any] = {"entity": entity, "id": str(rid), "name": getattr(rec, "name", None)}
    if entity == "deal":
        base.update(_deal_row(rec), contact=rec.contact.name if rec.contact else None, status=rec.status, priority=rec.priority, description=rec.description)
    elif entity == "lead":
        base.update(_lead_row(rec), email=rec.email, job_title=rec.job_title, description=rec.description, next_follow_up=rec.next_follow_up_at.isoformat() if rec.next_follow_up_at else None,
                    score_reasons=rec.score_reasons)
    elif entity == "contact":
        deals = db.session.query(Deal).filter(Deal.contact_id == rid, Deal.deleted_at.is_(None)).all() if _can("deals.read") else []
        base.update(email=rec.email, job_title=rec.job_title, company=rec.company.name if rec.company else None, description=rec.description,
                    deals=[{"name": d.name, "value": float(d.value), "status": d.status} for d in deals])
    else:
        deals = db.session.query(Deal).filter(Deal.company_id == rid, Deal.deleted_at.is_(None)).all() if _can("deals.read") else []
        base.update(industry=rec.industry, size=rec.size, deals=[{"name": d.name, "value": float(d.value), "status": d.status} for d in deals])
    base["recent_activity"] = [{"type": a.type, "title": a.title, "when": a.occurred_at.isoformat()} for a in acts]
    base["notes"] = [n.body[:400] for n in notes]
    return base


TOOL_SPECS: list[dict] = [
    {"name": "list_deals", "description": "List deals. Use for questions about pipeline, likely-to-close, highest-value, stalled or lost/won deals.",
     "input_schema": {"type": "object", "properties": {"status": {"type": "string", "enum": ["open", "won", "lost", "any"]}, "closing": {"type": "string", "enum": ["this_month", "next_30_days"]},
                                                      "sort": {"type": "string", "enum": ["value", "probability", "close_date"]}, "min_value": {"type": "number"}, "stale_days": {"type": "integer"}, "limit": {"type": "integer"}}}},
    {"name": "list_leads", "description": "List open leads, optionally those not contacted for N days or with a minimum score.",
     "input_schema": {"type": "object", "properties": {"status": {"type": "string"}, "stale_days": {"type": "integer"}, "min_score": {"type": "integer"}, "source": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "list_tasks", "description": "List the user's open tasks.", "input_schema": {"type": "object", "properties": {"view": {"type": "string", "enum": ["today", "overdue", "upcoming", "all"]}, "mine": {"type": "boolean"}}}},
    {"name": "pipeline_summary", "description": "Open pipeline value and weighted value by stage.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "team_performance", "description": "Per-salesperson wins, revenue, win rate and lead conversion.", "input_schema": {"type": "object", "properties": {"days": {"type": "integer"}}}},
    {"name": "revenue_trend", "description": "Revenue, wins/losses, conversion and new leads for the last N days.", "input_schema": {"type": "object", "properties": {"days": {"type": "integer"}}}},
    {"name": "search_crm", "description": "Find contacts, leads, companies and deals by name or email.", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "record_context", "description": "Full context (details, recent activity, notes) for one record.",
     "input_schema": {"type": "object", "properties": {"entity": {"type": "string", "enum": ["lead", "contact", "company", "deal"]}, "ident": {"type": "string"}}, "required": ["entity", "ident"]}},
]

TOOLS: dict[str, Callable[..., dict]] = {
    "list_deals": list_deals, "list_leads": list_leads, "list_tasks": list_tasks, "pipeline_summary": pipeline_summary, "team_performance": team_performance,
    "revenue_trend": revenue_trend, "search_crm": search_crm, "record_context": record_context,
}


def run_tool(name: str, args: dict) -> dict:
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"Unknown tool {name}"}
    allowed = {k: v for k, v in (args or {}).items() if k in fn.__code__.co_varnames[:fn.__code__.co_argcount]}
    if name == "list_deals" and allowed.get("status") == "any":
        allowed["status"] = "any"
    try:
        return fn(**allowed)
    except TypeError:
        return {"error": "Invalid arguments"}
