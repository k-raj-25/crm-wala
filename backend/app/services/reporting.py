"""Analytics queries shared by the dashboard and the Reports module. All queries are workspace-scoped."""
from __future__ import annotations

import datetime as dt
from typing import Any

from flask import g
from sqlalchemy import and_, case, func, or_

from app.extensions import db
from app.models import Activity, Company, Contact, Deal, Lead, Meeting, PipelineStage, Task, User, WorkspaceMember
from app.models.base import utcnow

REPORT_TYPES = {
    "revenue": "Revenue", "sales": "Sales", "leads": "Leads", "conversion": "Conversion", "pipeline": "Pipeline",
    "team_performance": "Team performance", "deal_velocity": "Deal velocity", "activity": "Activity", "forecast": "Forecast",
    "customer_acquisition": "Customer acquisition",
}
ADVANCED = {"team_performance", "deal_velocity", "forecast", "customer_acquisition", "activity", "conversion"}


def day_start(d: dt.datetime | None = None) -> dt.datetime:
    d = d or utcnow()
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def bucket_for(start: dt.datetime, end: dt.datetime) -> str:
    days = (end - start).days
    return "day" if days <= 14 else "week" if days <= 120 else "month"


def _fill(rows: dict, start: dt.datetime, end: dt.datetime, bucket: str, keys: list[str]) -> list[dict]:
    """Zero-fill the buckets so charts have continuous x axes."""
    out = []
    cur = start.replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "week":
        cur -= dt.timedelta(days=cur.weekday())
    elif bucket == "month":
        cur = cur.replace(day=1)
    while cur <= end:
        k = cur.date().isoformat()
        out.append({"period": k, **{c: rows.get(k, {}).get(c, 0) for c in keys}})
        if bucket == "day":
            cur += dt.timedelta(days=1)
        elif bucket == "week":
            cur += dt.timedelta(days=7)
        else:
            cur = (cur.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return out


def _won(ws, start, end, owner=None, pipeline=None):
    q = db.session.query(Deal).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "won", Deal.closed_at >= start, Deal.closed_at <= end)
    if owner:
        q = q.filter(Deal.owner_id == owner)
    if pipeline:
        q = q.filter(Deal.pipeline_id == pipeline)
    return q


def revenue_series(ws, start, end, bucket, owner=None, pipeline=None) -> list[dict]:
    b = func.date_trunc(bucket, Deal.closed_at)
    rows = _won(ws, start, end, owner, pipeline).with_entities(b, func.sum(Deal.value), func.count()).group_by(b).all()
    data = {r[0].date().isoformat(): {"revenue": float(r[1] or 0), "deals": r[2]} for r in rows}
    return _fill(data, start, end, bucket, ["revenue", "deals"])


def _delta(cur: float, prev: float) -> float | None:
    if prev == 0:
        return None if cur == 0 else 100.0
    return round((cur - prev) / prev * 100, 1)


def headline_metrics(ws, start, end) -> dict:
    span = end - start
    pstart, pend = start - span, start
    s = db.session

    def won(a, b):
        r = s.query(func.coalesce(func.sum(Deal.value), 0), func.count()).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "won",
                                                                              Deal.closed_at >= a, Deal.closed_at <= b).one()
        return float(r[0]), r[1]

    def lost(a, b):
        return s.query(func.count()).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "lost", Deal.closed_at >= a, Deal.closed_at <= b).scalar()

    def new_leads(a, b):
        return s.query(func.count()).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.created_at >= a, Lead.created_at <= b).scalar()

    rev, won_n = won(start, end)
    prev_rev, prev_won = won(pstart, pend)
    lost_n, prev_lost = lost(start, end), lost(pstart, pend)
    nl, pnl = new_leads(start, end), new_leads(pstart, pend)
    open_q = s.query(func.coalesce(func.sum(Deal.value), 0), func.count(), func.coalesce(func.sum(Deal.value * Deal.probability / 100.0), 0)).filter(
        Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "open").one()
    conv = round(won_n / (won_n + lost_n) * 100, 1) if (won_n + lost_n) else 0.0
    pconv = round(prev_won / (prev_won + prev_lost) * 100, 1) if (prev_won + prev_lost) else 0.0
    now = utcnow()
    due_today = s.query(func.count()).filter(Task.workspace_id == ws, Task.deleted_at.is_(None), Task.status != "completed", Task.due_at >= day_start(now),
                                             Task.due_at < day_start(now) + dt.timedelta(days=1)).scalar()
    return {
        "revenue": {"value": rev, "delta": _delta(rev, prev_rev)},
        "pipeline_value": {"value": float(open_q[0]), "weighted": float(open_q[2])},
        "deals_won": {"value": won_n, "delta": _delta(won_n, prev_won)},
        "deals_lost": {"value": lost_n, "delta": _delta(lost_n, prev_lost)},
        "conversion_rate": {"value": conv, "delta": round(conv - pconv, 1)},
        "new_leads": {"value": nl, "delta": _delta(nl, pnl)},
        "active_deals": {"value": open_q[1]},
        "tasks_due_today": {"value": due_today},
    }


def pipeline_by_stage(ws, pipeline_id=None) -> list[dict]:
    q = db.session.query(PipelineStage.name, PipelineStage.color, PipelineStage.position, func.count(Deal.id), func.coalesce(func.sum(Deal.value), 0),
                         func.coalesce(func.sum(Deal.value * Deal.probability / 100.0), 0)).outerjoin(
        Deal, and_(Deal.stage_id == PipelineStage.id, Deal.deleted_at.is_(None), Deal.status == "open")).filter(
        PipelineStage.workspace_id == ws, PipelineStage.kind == "open")
    if pipeline_id:
        q = q.filter(PipelineStage.pipeline_id == pipeline_id)
    else:
        from app.models import Pipeline

        default = db.session.query(Pipeline.id).filter_by(workspace_id=ws, is_default=True, deleted_at=None).scalar()
        if default:
            q = q.filter(PipelineStage.pipeline_id == default)
    rows = q.group_by(PipelineStage.id).order_by(PipelineStage.position).all()
    return [{"stage": r[0], "color": r[1], "deals": r[3], "value": float(r[4]), "weighted": float(r[5])} for r in rows]


def lead_funnel(ws, start, end) -> list[dict]:
    rows = dict(db.session.query(Lead.status, func.count()).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.created_at >= start,
                                                                   Lead.created_at <= end).group_by(Lead.status).all())
    order = [s["key"] for s in (g.workspace.settings or {}).get("lead_statuses", [])] or list(rows)
    return [{"status": k, "count": rows.get(k, 0)} for k in order]


def sales_funnel(ws, start, end) -> list[dict]:
    """Deals created in range, by the furthest stage reached (current stage position as proxy)."""
    from app.api.v1.deals import default_pipeline

    pid = default_pipeline().id
    stages = db.session.query(PipelineStage).filter_by(pipeline_id=pid).order_by(PipelineStage.position).all()
    counts = dict(db.session.query(Deal.stage_id, func.count()).filter(Deal.workspace_id == ws, Deal.pipeline_id == pid, Deal.deleted_at.is_(None),
                                                                    Deal.created_at >= start, Deal.created_at <= end).group_by(Deal.stage_id).all())
    open_stages = [s for s in stages if s.kind != "lost"]
    out, cumulative = [], 0
    for s in reversed(open_stages):  # a deal in Negotiation also "reached" earlier stages
        cumulative += counts.get(s.id, 0)
        out.append({"stage": s.name, "count": cumulative, "color": s.color})
    return list(reversed(out))


def deal_velocity(ws, start, end, bucket) -> list[dict]:
    b = func.date_trunc("month" if bucket != "day" else "week", Deal.closed_at)
    rows = db.session.query(b, func.avg(func.extract("epoch", Deal.closed_at - Deal.created_at) / 86400.0), func.count()).filter(
        Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "won", Deal.closed_at >= start, Deal.closed_at <= end).group_by(b).order_by(b).all()
    return [{"period": r[0].date().isoformat(), "avg_days": round(float(r[1] or 0), 1), "deals": r[2]} for r in rows]


def forecast(ws, months: int = 6) -> list[dict]:
    today = utcnow().date().replace(day=1)
    out = []
    for i in range(months):
        a = (today + dt.timedelta(days=32 * i)).replace(day=1)
        b = (a + dt.timedelta(days=32)).replace(day=1)
        r = db.session.query(func.coalesce(func.sum(Deal.value), 0), func.coalesce(func.sum(Deal.value * Deal.probability / 100.0), 0),
                             func.coalesce(func.sum(case((Deal.probability >= 70, Deal.value), else_=0)), 0), func.count()).filter(
            Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "open", Deal.expected_close_date >= a, Deal.expected_close_date < b).one()
        out.append({"period": a.isoformat(), "best_case": float(r[0]), "weighted": round(float(r[1]), 2), "commit": float(r[2]), "deals": r[3]})
    return out


def activity_feed(ws, limit: int = 15) -> list[dict]:
    from app.api.v1.crm_helpers import activity_dicts

    rows = db.session.query(Activity).filter(Activity.workspace_id == ws, Activity.type != "system").order_by(Activity.occurred_at.desc()).limit(limit).all()
    return activity_dicts(rows)


def todays_focus(ws, user_id=None) -> dict:
    now = utcnow()
    start, end = day_start(now), day_start(now) + dt.timedelta(days=1)
    s = db.session

    def mine(q, col):
        return q.filter(col == user_id) if user_id else q

    follow_tasks = mine(s.query(Task).filter(Task.workspace_id == ws, Task.deleted_at.is_(None), Task.status != "completed", Task.kind == "follow_up",
                                             Task.due_at >= start, Task.due_at < end), Task.assignee_id).all()
    follow_leads = mine(s.query(Lead).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.status.in_(("new", "contacted", "qualified")),
                                             Lead.next_follow_up_at >= start, Lead.next_follow_up_at < end), Lead.owner_id).all()
    meetings = mine(s.query(Meeting).filter(Meeting.workspace_id == ws, Meeting.deleted_at.is_(None), Meeting.status == "scheduled", Meeting.starts_at >= now - dt.timedelta(hours=1),
                                            Meeting.starts_at < end), Meeting.organizer_id).order_by(Meeting.starts_at).all()
    stale = now - dt.timedelta(days=7)
    attention = mine(s.query(Deal).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "open",
                                          or_(Deal.last_activity_at < stale, Deal.last_activity_at.is_(None), Deal.expected_close_date < now.date())),
                     Deal.owner_id).order_by(Deal.value.desc()).limit(20).all()
    overdue = mine(s.query(Task).filter(Task.workspace_id == ws, Task.deleted_at.is_(None), Task.status != "completed", Task.due_at < start), Task.assignee_id).order_by(Task.due_at).all()
    from app.models import Unit

    holds = mine(s.query(Unit).filter(Unit.workspace_id == ws, Unit.deleted_at.is_(None), Unit.status == "on_hold", Unit.hold_until.isnot(None),
                                      Unit.hold_until < now + dt.timedelta(hours=24)), Unit.held_by).order_by(Unit.hold_until).all()
    return {
        "holds_expiring": {"count": len(holds), "items": [{"type": "unit", "id": str(u.id), "title": f"{u.name} hold", "due_at": u.hold_until.isoformat(),
                                                           "url": f"/app/projects/{u.project_id}?tower={u.tower_id}&unit={u.id}"} for u in holds[:5]]},
        "follow_ups": {"count": len(follow_tasks) + len(follow_leads), "items": [
            *[{"type": "task", "id": str(t.id), "title": t.title, "due_at": t.due_at.isoformat(), "url": "/app/tasks"} for t in follow_tasks[:5]],
            *[{"type": "lead", "id": str(l.id), "title": f"Follow up with {l.name}", "due_at": l.next_follow_up_at.isoformat(), "url": f"/app/leads/{l.id}"} for l in follow_leads[:5]]][:6]},
        "meetings": {"count": len(meetings), "items": [{"type": m.kind, "id": str(m.id), "title": m.title, "starts_at": m.starts_at.isoformat(), "url": "/app/calendar"} for m in meetings[:5]]},
        "deals_attention": {"count": len(attention), "items": [{"type": "deal", "id": str(d.id), "title": d.name, "value": float(d.value), "currency": d.currency,
                                                                "reason": "Past expected close date" if d.expected_close_date and d.expected_close_date < now.date() else "No activity in 7+ days",
                                                                "url": f"/app/deals/{d.id}"} for d in attention[:5]]},
        "overdue_tasks": {"count": len(overdue), "items": [{"type": "task", "id": str(t.id), "title": t.title, "due_at": t.due_at.isoformat(), "url": "/app/tasks"} for t in overdue[:5]]},
    }


# ---- Reports ----------------------------------------------------------------------------

def _col(key, label, kind="text"):
    return {"key": key, "label": label, "type": kind}


def run_report(rtype: str, start: dt.datetime, end: dt.datetime, owner=None, pipeline=None) -> dict:
    ws = g.workspace.id
    bucket = bucket_for(start, end)
    s = db.session
    if rtype == "revenue":
        series = revenue_series(ws, start, end, bucket, owner, pipeline)
        total = sum(r["revenue"] for r in series)
        n = sum(r["deals"] for r in series)
        return {"title": "Revenue", "columns": [_col("period", "Period", "date"), _col("revenue", "Revenue", "currency"), _col("deals", "Deals won", "number")], "rows": series,
                "chart": {"type": "area", "x": "period", "series": [{"key": "revenue", "label": "Revenue"}]},
                "summary": [{"label": "Total revenue", "value": total, "format": "currency"}, {"label": "Deals won", "value": n, "format": "number"},
                            {"label": "Average deal size", "value": round(total / n, 2) if n else 0, "format": "currency"}]}
    if rtype in ("sales", "team_performance"):
        users = {u.id: u.name for u in s.query(User).join(WorkspaceMember, WorkspaceMember.user_id == User.id).filter(WorkspaceMember.workspace_id == ws)}
        won = {r[0]: (r[1], float(r[2] or 0)) for r in s.query(Deal.owner_id, func.count(), func.sum(Deal.value)).filter(
            Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "won", Deal.closed_at >= start, Deal.closed_at <= end).group_by(Deal.owner_id)}
        lost = dict(s.query(Deal.owner_id, func.count()).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "lost", Deal.closed_at >= start,
                                                                Deal.closed_at <= end).group_by(Deal.owner_id).all())
        openv = {r[0]: (r[1], float(r[2] or 0)) for r in s.query(Deal.owner_id, func.count(), func.sum(Deal.value)).filter(
            Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "open").group_by(Deal.owner_id)}
        rows = []
        leads_c = dict(s.query(Lead.owner_id, func.count()).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.created_at >= start, Lead.created_at <= end).group_by(Lead.owner_id))
        conv_c = dict(s.query(Lead.owner_id, func.count()).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.converted_at >= start, Lead.converted_at <= end).group_by(Lead.owner_id))
        acts = dict(s.query(Activity.user_id, func.count()).filter(Activity.workspace_id == ws, Activity.occurred_at >= start, Activity.occurred_at <= end).group_by(Activity.user_id))
        tasks_done = dict(s.query(Task.assignee_id, func.count()).filter(Task.workspace_id == ws, Task.deleted_at.is_(None), Task.completed_at >= start, Task.completed_at <= end).group_by(Task.assignee_id))
        for uid, name in users.items():
            w, l = won.get(uid, (0, 0.0)), lost.get(uid, 0)
            rows.append({"rep": name, "deals_won": w[0], "revenue": w[1], "deals_lost": l, "win_rate": round(w[0] / (w[0] + l) * 100, 1) if (w[0] + l) else 0,
                         "open_deals": openv.get(uid, (0, 0))[0], "open_value": openv.get(uid, (0, 0))[1], "new_leads": leads_c.get(uid, 0),
                         "leads_converted": conv_c.get(uid, 0), "activities": acts.get(uid, 0), "tasks_completed": tasks_done.get(uid, 0)})
        rows.sort(key=lambda r: -r["revenue"])
        cols = [_col("rep", "Rep"), _col("deals_won", "Won", "number"), _col("deals_lost", "Lost", "number"), _col("win_rate", "Win rate", "percent"), _col("revenue", "Revenue", "currency"),
                _col("open_deals", "Open deals", "number"), _col("open_value", "Open value", "currency")]
        if rtype == "team_performance":
            cols += [_col("new_leads", "New leads", "number"), _col("leads_converted", "Converted", "number"), _col("activities", "Activities", "number"), _col("tasks_completed", "Tasks done", "number")]
        return {"title": REPORT_TYPES[rtype], "columns": cols, "rows": rows, "chart": {"type": "bar", "x": "rep", "series": [{"key": "revenue", "label": "Revenue"}]},
                "summary": [{"label": "Revenue", "value": sum(r["revenue"] for r in rows), "format": "currency"}, {"label": "Deals won", "value": sum(r["deals_won"] for r in rows), "format": "number"}]}
    if rtype == "leads":
        b = func.date_trunc(bucket, Lead.created_at)
        series = {r[0].date().isoformat(): {"leads": r[1]} for r in s.query(b, func.count()).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.created_at >= start,
                                                                                                  Lead.created_at <= end).group_by(b)}
        rows = _fill(series, start, end, bucket, ["leads"])
        by_source = s.query(func.coalesce(Lead.source, "unknown"), func.count(), func.avg(Lead.score)).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.created_at >= start,
                                                                                                         Lead.created_at <= end).group_by(Lead.source).order_by(func.count().desc()).all()
        return {"title": "Leads", "columns": [_col("period", "Period", "date"), _col("leads", "New leads", "number")], "rows": rows,
                "chart": {"type": "bar", "x": "period", "series": [{"key": "leads", "label": "New leads"}]},
                "summary": [{"label": "New leads", "value": sum(r["leads"] for r in rows), "format": "number"}],
                "breakdown": {"title": "By source", "rows": [{"label": r[0].replace("_", " "), "value": r[1], "avg_score": round(float(r[2] or 0))} for r in by_source]}}
    if rtype == "conversion":
        funnel = lead_funnel(ws, start, end)
        total = sum(f["count"] for f in funnel)
        conv = next((f["count"] for f in funnel if f["status"] == "converted"), 0)
        rows = [{"status": f["status"].replace("_", " ").title(), "count": f["count"], "share": round(f["count"] / total * 100, 1) if total else 0} for f in funnel]
        src = s.query(func.coalesce(Lead.source, "unknown"), func.count(), func.count(Lead.converted_at)).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.created_at >= start,
                                                                                                             Lead.created_at <= end).group_by(Lead.source).all()
        return {"title": "Conversion", "columns": [_col("status", "Status"), _col("count", "Leads", "number"), _col("share", "Share", "percent")], "rows": rows,
                "chart": {"type": "bar", "x": "status", "series": [{"key": "count", "label": "Leads"}]},
                "summary": [{"label": "Lead → customer", "value": round(conv / total * 100, 1) if total else 0, "format": "percent"}, {"label": "Leads", "value": total, "format": "number"}],
                "breakdown": {"title": "Conversion by source", "rows": [{"label": r[0].replace("_", " "), "value": round(r[2] / r[1] * 100, 1) if r[1] else 0, "format": "percent"} for r in src]}}
    if rtype == "pipeline":
        rows = pipeline_by_stage(ws, pipeline)
        return {"title": "Pipeline", "columns": [_col("stage", "Stage"), _col("deals", "Deals", "number"), _col("value", "Value", "currency"), _col("weighted", "Weighted", "currency")], "rows": rows,
                "chart": {"type": "bar", "x": "stage", "series": [{"key": "value", "label": "Value"}, {"key": "weighted", "label": "Weighted"}]},
                "summary": [{"label": "Open pipeline", "value": sum(r["value"] for r in rows), "format": "currency"}, {"label": "Weighted", "value": sum(r["weighted"] for r in rows), "format": "currency"}]}
    if rtype == "deal_velocity":
        rows = deal_velocity(ws, start, end, bucket)
        avg = round(sum(r["avg_days"] * r["deals"] for r in rows) / max(sum(r["deals"] for r in rows), 1), 1)
        return {"title": "Deal velocity", "columns": [_col("period", "Period", "date"), _col("avg_days", "Avg. days to close", "number"), _col("deals", "Deals won", "number")], "rows": rows,
                "chart": {"type": "line", "x": "period", "series": [{"key": "avg_days", "label": "Avg days to close"}]}, "summary": [{"label": "Average sales cycle (days)", "value": avg, "format": "number"}]}
    if rtype == "activity":
        b = func.date_trunc(bucket, Activity.occurred_at)
        rows_ = s.query(b, Activity.type, func.count()).filter(Activity.workspace_id == ws, Activity.occurred_at >= start, Activity.occurred_at <= end,
                                                              Activity.type.in_(("email", "call", "meeting", "note", "task_completed"))).group_by(b, Activity.type).all()
        data: dict[str, dict] = {}
        for p, t, c in rows_:
            data.setdefault(p.date().isoformat(), {})[t] = c
        keys = ["email", "call", "meeting", "note", "task_completed"]
        rows = _fill(data, start, end, bucket, keys)
        return {"title": "Activity", "columns": [_col("period", "Period", "date"), *[_col(k, k.replace("_", " ").title(), "number") for k in keys]], "rows": rows,
                "chart": {"type": "bar", "stacked": True, "x": "period", "series": [{"key": k, "label": k.replace("_", " ").title()} for k in keys]},
                "summary": [{"label": k.replace("_", " ").title(), "value": sum(r[k] for r in rows), "format": "number"} for k in keys]}
    if rtype == "forecast":
        rows = forecast(ws)
        return {"title": "Revenue forecast", "columns": [_col("period", "Month", "date"), _col("deals", "Deals", "number"), _col("commit", "Commit (≥70%)", "currency"), _col("weighted", "Weighted", "currency"),
                                                       _col("best_case", "Best case", "currency")], "rows": rows,
                "chart": {"type": "bar", "x": "period", "series": [{"key": "commit", "label": "Commit"}, {"key": "weighted", "label": "Weighted"}, {"key": "best_case", "label": "Best case"}]},
                "summary": [{"label": "Weighted (6 mo)", "value": sum(r["weighted"] for r in rows), "format": "currency"}, {"label": "Commit (6 mo)", "value": sum(r["commit"] for r in rows), "format": "currency"}]}
    if rtype == "customer_acquisition":
        first_won = db.session.query(Deal.company_id, func.min(Deal.closed_at).label("first")).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "won",
                                                                                                    Deal.company_id.isnot(None)).group_by(Deal.company_id).subquery()
        b = func.date_trunc("month" if bucket != "day" else "week", first_won.c.first)
        rows_ = db.session.query(b, func.count()).filter(first_won.c.first >= start, first_won.c.first <= end).group_by(b).order_by(b).all()
        rows = [{"period": r[0].date().isoformat(), "new_customers": r[1]} for r in rows_]
        contacts = db.session.query(func.count()).filter(Contact.workspace_id == ws, Contact.deleted_at.is_(None), Contact.created_at >= start, Contact.created_at <= end).scalar()
        return {"title": "Customer acquisition", "columns": [_col("period", "Period", "date"), _col("new_customers", "New customers", "number")], "rows": rows,
                "chart": {"type": "bar", "x": "period", "series": [{"key": "new_customers", "label": "New customers"}]},
                "summary": [{"label": "New customers", "value": sum(r["new_customers"] for r in rows), "format": "number"}, {"label": "New contacts", "value": contacts, "format": "number"}]}
    raise ValueError(rtype)
