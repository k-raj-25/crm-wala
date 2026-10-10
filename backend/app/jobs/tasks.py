from __future__ import annotations

import datetime as dt
import logging
import time
from functools import wraps

from app.celery_app import celery
from app.extensions import db

log = logging.getLogger("app.jobs")
_app = None


def flask_app():
    global _app
    if _app is None:
        from app import create_app

        _app = create_app()
    return _app


def job(name: str):
    """Register a task that runs in an app context, bypasses tenant RLS (jobs scope per-workspace explicitly) and logs its outcome."""

    def deco(fn):
        @celery.task(name=f"jobs.{name}")
        @wraps(fn)
        def wrapper(*a, **kw):
            from flask import has_app_context

            from app.core.tenant import bypass_scope
            from app.models import JobLog

            def run():
                t0 = time.time()
                status, err, detail = "success", None, {}
                try:
                    with bypass_scope():
                        detail = fn(*a, **kw) or {}
                except Exception as e:
                    db.session.rollback()
                    status, err = "failed", repr(e)[:1000]
                    log.exception("job %s failed", name)
                with bypass_scope():
                    db.session.add(JobLog(name=name, status=status, duration_ms=int((time.time() - t0) * 1000), error=err, detail=detail if isinstance(detail, dict) else {}))
                    db.session.commit()
                return detail

            if has_app_context():
                return run()
            with flask_app().app_context():
                return run()

        return wrapper

    return deco


@job("billing_lifecycle")
def billing_lifecycle():
    from app.services.billing.core import run_lifecycle

    return run_lifecycle()


@job("resume_automations")
def resume_automations():
    from app.services.automation import resume_due

    return {"resumed": resume_due()}


@job("send_scheduled_emails")
def send_scheduled_emails():
    from app.core.tenant import tenant_scope
    from app.models import Email, User
    from app.models.base import utcnow
    from app.services import activities, mailbox

    due = [(e.id, e.workspace_id) for e in db.session.query(Email).filter(Email.status == "scheduled", Email.scheduled_at <= utcnow(), Email.deleted_at.is_(None)).limit(200)]
    sent = 0
    for eid, wid in due:
        with tenant_scope(wid):
            e = db.session.get(Email, eid)
            sender = db.session.get(User, e.user_id)
            mailbox.deliver(e, sender)
            if e.status == "sent":
                activities.log_activity("email", f"Email sent: {e.subject}", workspace_id=wid, user_id=e.user_id, body=e.body[:500], lead_id=e.lead_id, contact_id=e.contact_id,
                                        company_id=e.company_id, deal_id=e.deal_id, data={"email_id": str(e.id)})
                mailbox.touch_contacted(e, utcnow())
                sent += 1
            db.session.commit()
    return {"sent": sent}


@job("send_reminders")
def send_reminders():
    """Meeting reminders (30 min before) and task-due reminders (when due within the hour)."""
    from app.core.tenant import tenant_scope
    from app.models import Meeting, Task, User
    from app.models.base import utcnow
    from app.services import email as email_service
    from app.services.notifications import notify

    now, n = utcnow(), 0
    for mid, wid in [(m.id, m.workspace_id) for m in db.session.query(Meeting).filter(Meeting.status == "scheduled", Meeting.deleted_at.is_(None), Meeting.reminder_sent_at.is_(None),
                                                                                        Meeting.starts_at > now, Meeting.starts_at <= now + dt.timedelta(minutes=30)).limit(500)]:
        with tenant_scope(wid):
            m = db.session.get(Meeting, mid)
            if m.organizer_id:
                u = db.session.get(User, m.organizer_id)
                notify(wid, [m.organizer_id], "meeting_reminder", f"Starting soon: {m.title}", f"At {m.starts_at:%I:%M %p UTC}", "/app/calendar")
                if u:
                    email_service.send_template("meeting_reminder", u.email, {"name": u.name, "title": m.title, "time": m.starts_at.strftime("%d %b, %I:%M %p UTC"), "link": "/app/calendar"}, workspace_id=wid)
            m.reminder_sent_at = now
            db.session.commit()
            n += 1
    for tid, wid in [(t.id, t.workspace_id) for t in db.session.query(Task).filter(Task.status != "completed", Task.deleted_at.is_(None), Task.reminder_sent_at.is_(None), Task.due_at.isnot(None),
                                                                                    Task.due_at <= now + dt.timedelta(hours=1), Task.due_at > now - dt.timedelta(days=1)).limit(500)]:
        with tenant_scope(wid):
            t = db.session.get(Task, tid)
            if t.assignee_id:
                u = db.session.get(User, t.assignee_id)
                notify(wid, [t.assignee_id], "task_assigned", f"Task due soon: {t.title}", f"Due {t.due_at:%d %b %I:%M %p UTC}", "/app/tasks")
                if u:
                    email_service.send_template("task_reminder", u.email, {"name": u.name, "title": t.title, "due": t.due_at.strftime("%d %b, %I:%M %p UTC"), "link": "/app/tasks"}, workspace_id=wid)
            t.reminder_sent_at = now
            db.session.commit()
            n += 1
    return {"reminders": n}


@job("send_scheduled_reports")
def send_scheduled_reports():
    from flask import current_app, g

    from app.api.v1.analytics import render_pdf
    from app.core.tenant import tenant_scope
    from app.models import SavedReport, User, Workspace
    from app.models.base import utcnow
    from app.services import email as email_service
    from app.services import reporting

    now = utcnow()
    gap = {"daily": dt.timedelta(hours=23), "weekly": dt.timedelta(days=6, hours=23), "monthly": dt.timedelta(days=27)}
    sent = 0
    for rid, wid in [(r.id, r.workspace_id) for r in db.session.query(SavedReport).filter(SavedReport.schedule.isnot(None)).all()]:
        with tenant_scope(wid):
            r = db.session.get(SavedReport, rid)
            if r.last_sent_at and now - r.last_sent_at < gap[r.schedule]:
                continue
            ws = db.session.get(Workspace, wid)
            g.workspace = ws
            days = {"daily": 1, "weekly": 7, "monthly": 30}[r.schedule]
            rep = reporting.run_report(r.report_type, now - dt.timedelta(days=days), now)
            summary = " · ".join(f"{s['label']}: {s['value']}" for s in rep.get("summary", [])[:4])
            owner = db.session.get(User, r.owner_id)
            for to in set(r.recipients or ([owner.email] if owner else [])):
                email_service.send_template("report", to, {"report": r.name, "summary": summary, "link": f"{current_app.config['WEB_ORIGIN']}/app/reports"}, workspace_id=wid)
            r.last_sent_at = now
            db.session.commit()
            sent += 1
    return {"sent": sent}


@job("release_expired_holds")
def release_expired_holds():
    from app.services import inventory

    return {"released": inventory.release_expired_holds()}


@job("housekeeping")
def housekeeping():
    from app.models import AnalyticsEvent, ApiErrorLog, AuthEvent, EmailLog, ImpersonationGrant, JobLog, UserSession, WebhookEvent
    from app.models.base import utcnow

    now = utcnow()
    out = {}
    for model, days, col in ((ApiErrorLog, 30, "created_at"), (JobLog, 30, "created_at"), (EmailLog, 90, "created_at"), (AuthEvent, 180, "created_at"), (WebhookEvent, 90, "created_at")):
        out[model.__tablename__] = db.session.query(model).filter(getattr(model, col) < now - dt.timedelta(days=days)).delete()
    out["sessions"] = db.session.query(UserSession).filter(UserSession.expires_at < now - dt.timedelta(days=7)).delete()
    out["impersonation_grants"] = db.session.query(ImpersonationGrant).filter(ImpersonationGrant.expires_at < now - dt.timedelta(days=1)).delete()
    return out
