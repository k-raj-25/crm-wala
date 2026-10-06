"""Deterministic AI-style features: next-best-action, churn risk, data cleanup, pipeline diagnosis.

These run without any LLM (so they're free, instant and explainable). An LLM can optionally narrate them.
"""
from __future__ import annotations

import datetime as dt
import re

from flask import g
from sqlalchemy import func, or_

from app.extensions import db
from app.models import Activity, Company, Contact, Deal, Lead, Task
from app.models.base import utcnow
from app.services import reporting


def next_best_actions(limit: int = 8) -> list[dict]:
    ws, now = g.workspace.id, utcnow()
    out: list[dict] = []
    mine = lambda col: col == g.user.id  # noqa: E731
    for d in db.session.query(Deal).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "open", mine(Deal.owner_id), Deal.expected_close_date <= now.date() + dt.timedelta(days=7),
                                            Deal.expected_close_date >= now.date()).order_by(Deal.value.desc()).limit(3):
        out.append({"priority": 1, "kind": "deal_closing", "title": f"Close out {d.name}", "reason": f"Expected to close {d.expected_close_date:%d %b} · {d.currency} {float(d.value):,.0f} at {d.probability}%", "url": f"/app/deals/{d.id}", "cta": "Open deal"})
    for d in db.session.query(Deal).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "open", mine(Deal.owner_id), Deal.expected_close_date < now.date()).order_by(Deal.value.desc()).limit(3):
        out.append({"priority": 1, "kind": "deal_overdue", "title": f"{d.name} is past its close date", "reason": f"Expected {d.expected_close_date:%d %b}. Update the date or push for a decision.", "url": f"/app/deals/{d.id}", "cta": "Review deal"})
    for d in db.session.query(Deal).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "open", mine(Deal.owner_id),
                                            or_(Deal.last_activity_at < now - dt.timedelta(days=7), Deal.last_activity_at.is_(None))).order_by(Deal.value.desc()).limit(3):
        days = (now - d.last_activity_at).days if d.last_activity_at else None
        out.append({"priority": 2, "kind": "deal_stalled", "title": f"Re-engage {d.name}", "reason": f"No activity {'for ' + str(days) + ' days' if days else 'recorded'}. A quick check-in keeps the deal moving.", "url": f"/app/deals/{d.id}", "cta": "Send follow-up"})
    for l in db.session.query(Lead).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.status == "new", mine(Lead.owner_id), Lead.score >= 60).order_by(Lead.score.desc()).limit(3):
        out.append({"priority": 2, "kind": "hot_lead", "title": f"Contact {l.name} — hot lead", "reason": f"Score {l.score}/100 and not contacted yet.", "url": f"/app/leads/{l.id}", "cta": "Open lead"})
    overdue = db.session.query(func.count(Task.id)).filter(Task.workspace_id == ws, Task.deleted_at.is_(None), Task.status != "completed", mine(Task.assignee_id), Task.due_at < reporting.day_start(now)).scalar()
    if overdue:
        out.append({"priority": 3, "kind": "overdue_tasks", "title": f"Clear {overdue} overdue task{'s' if overdue != 1 else ''}", "reason": "Overdue follow-ups are the #1 reason deals go cold.", "url": "/app/tasks", "cta": "View tasks"})
    out.sort(key=lambda a: a["priority"])
    return out[:limit]


def churn_risk(inactive_days: int = 45, limit: int = 10) -> list[dict]:
    """Customers (companies with a won deal) with no recent activity, ranked by revenue at risk."""
    ws, now = g.workspace.id, utcnow()
    won = db.session.query(Deal.company_id, func.sum(Deal.value).label("rev"), func.max(Deal.closed_at).label("last_won")).filter(
        Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "won", Deal.company_id.isnot(None)).group_by(Deal.company_id).subquery()
    rows = db.session.query(Company, won.c.rev, won.c.last_won).join(won, won.c.company_id == Company.id).filter(Company.deleted_at.is_(None)).all()
    out = []
    for c, rev, last_won in rows:
        last = c.last_activity_at or last_won
        days = (now - last).days if last else 999
        if days < inactive_days:
            continue
        open_deals = db.session.query(func.count(Deal.id)).filter(Deal.company_id == c.id, Deal.status == "open", Deal.deleted_at.is_(None)).scalar()
        risk = min(100, int(40 + days / 3 + (0 if open_deals else 15)))
        out.append({"company_id": str(c.id), "name": c.name, "revenue": float(rev or 0), "days_inactive": days, "open_deals": open_deals, "risk": risk,
                    "reason": f"No activity for {days} days" + ("" if open_deals else " and no open deals"), "url": f"/app/companies/{c.id}"})
    out.sort(key=lambda r: (-r["risk"], -r["revenue"]))
    return out[:limit]


def data_cleanup() -> list[dict]:
    from app.api.v1.data import find_duplicate_groups

    ws = g.workspace.id
    s = db.session
    out: list[dict] = []
    c = lambda q: q.scalar() or 0  # noqa: E731
    dup_c, dup_l = len(find_duplicate_groups("contact")), len(find_duplicate_groups("lead"))
    if dup_c or dup_l:
        out.append({"kind": "duplicates", "count": dup_c + dup_l, "title": "Possible duplicates", "detail": f"{dup_c} contact group(s) and {dup_l} lead group(s) look like duplicates.", "url": "/app/settings/data"})
    n = c(s.query(func.count(Contact.id)).filter(Contact.workspace_id == ws, Contact.deleted_at.is_(None), Contact.email.is_(None), Contact.phone.is_(None)))
    if n:
        out.append({"kind": "missing_contact_info", "count": n, "title": "Contacts with no email or phone", "detail": "They can't be reached — add details or remove them.", "url": "/app/contacts?q="})
    n = c(s.query(func.count(Lead.id)).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.owner_id.is_(None)))
    if n:
        out.append({"kind": "unassigned_leads", "count": n, "title": "Leads without an owner", "detail": "Assign them so nobody falls through the cracks.", "url": "/app/leads"})
    n = c(s.query(func.count(Lead.id)).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.status.in_(("new", "contacted")), Lead.created_at < utcnow() - dt.timedelta(days=60)))
    if n:
        out.append({"kind": "stale_leads", "count": n, "title": "Leads older than 60 days still open", "detail": "Qualify, follow up, or mark them lost to keep your pipeline honest.", "url": "/app/leads?stale_days=60"})
    n = c(s.query(func.count(Deal.id)).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "open", Deal.expected_close_date.is_(None)))
    if n:
        out.append({"kind": "deals_no_close_date", "count": n, "title": "Open deals without a close date", "detail": "Forecasts need an expected close date.", "url": "/app/deals"})
    bad_case = 0
    for (first, last) in s.query(Contact.first_name, Contact.last_name).filter(Contact.workspace_id == ws, Contact.deleted_at.is_(None)).limit(5000):
        for part in (first, last):
            if part and (part.islower() or part.isupper()) and len(part) > 2:
                bad_case += 1
                break
    if bad_case:
        out.append({"kind": "name_casing", "count": bad_case, "title": "Names with inconsistent capitalisation", "detail": "e.g. “john smith” or “JOHN”. Tidy names look more professional in emails.", "url": "/app/contacts"})
    bad_phone = sum(1 for (p,) in s.query(Contact.phone).filter(Contact.workspace_id == ws, Contact.deleted_at.is_(None), Contact.phone.isnot(None)).limit(5000) if not re.match(r"^\+?[\d\s().-]{7,}$", p or ""))
    if bad_phone:
        out.append({"kind": "bad_phone", "count": bad_phone, "title": "Phone numbers that look invalid", "detail": "Use international format, e.g. +91 98765 43210.", "url": "/app/contacts"})
    return out


def pipeline_diagnosis(days: int = 30) -> dict:
    """Why is the pipeline moving the way it is? Compares the last `days` with the previous period."""
    ws, now = g.workspace.id, utcnow()
    cur_start, prev_start = now - dt.timedelta(days=days), now - dt.timedelta(days=days * 2)
    s = db.session

    def created(a, b):
        r = s.query(func.count(), func.coalesce(func.sum(Deal.value), 0)).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.created_at >= a, Deal.created_at < b).one()
        return r[0], float(r[1])

    def closed(a, b, status):
        r = s.query(func.count(), func.coalesce(func.sum(Deal.value), 0)).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == status, Deal.closed_at >= a, Deal.closed_at < b).one()
        return r[0], float(r[1])

    cn, cv = created(cur_start, now)
    pn, pv = created(prev_start, cur_start)
    cw, cwv = closed(cur_start, now, "won")
    pw, pwv = closed(prev_start, cur_start, "won")
    cl, _ = closed(cur_start, now, "lost")
    pl, _ = closed(prev_start, cur_start, "lost")
    stalled = s.query(func.count(), func.coalesce(func.sum(Deal.value), 0)).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "open",
                                                                                     or_(Deal.last_activity_at < now - dt.timedelta(days=14), Deal.last_activity_at.is_(None))).one()
    new_leads = s.query(func.count()).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.created_at >= cur_start).scalar()
    prev_leads = s.query(func.count()).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.created_at >= prev_start, Lead.created_at < cur_start).scalar()
    findings = []

    def pct(a, b):
        return None if b == 0 else round((a - b) / b * 100)

    if pn and cn < pn:
        findings.append({"severity": "high" if cn < pn * 0.7 else "medium", "title": "Fewer new deals entering the pipeline", "detail": f"{cn} new deals vs {pn} in the previous {days} days ({pct(cn, pn)}%)."})
    if prev_leads and new_leads < prev_leads:
        findings.append({"severity": "medium", "title": "Lead flow is down", "detail": f"{new_leads} new leads vs {prev_leads} previously ({pct(new_leads, prev_leads)}%). Top-of-funnel drives pipeline 30–60 days later."})
    if (cw + cl) and (pw + pl) and cw / (cw + cl) < pw / (pw + pl):
        findings.append({"severity": "high", "title": "Win rate dropped", "detail": f"{round(cw / (cw + cl) * 100)}% now vs {round(pw / (pw + pl) * 100)}% before."})
    if stalled[0]:
        findings.append({"severity": "high" if stalled[0] > 5 else "medium", "title": "Stalled deals", "detail": f"{stalled[0]} open deals (worth {float(stalled[1]):,.0f}) have had no activity for 14+ days."})
    if pwv and cwv < pwv:
        findings.append({"severity": "medium", "title": "Closed revenue is lower", "detail": f"{cwv:,.0f} won vs {pwv:,.0f} in the previous period ({pct(cwv, pwv)}%)."})
    direction = "declining" if (pv and cv < pv) or (pwv and cwv < pwv) else "stable or growing"
    return {"days": days, "direction": direction, "created": {"current": cn, "previous": pn, "value_current": cv, "value_previous": pv}, "won": {"current": cw, "previous": pw, "value_current": cwv, "value_previous": pwv},
            "findings": findings or [{"severity": "low", "title": "No major red flags", "detail": "New deals, lead flow and win rate are in line with the previous period."}]}
