"""Scheduler hook for hosts without a background worker (e.g. Render's free tier).

An external scheduler (GitHub Actions, cron-job.org...) POSTs here every ~15 minutes with the shared secret and the
periodic jobs run inline. Disabled (404) unless JOBS_TOKEN is set. With a real Celery worker + beat you don't need this."""
from __future__ import annotations

import hmac

from flask import Blueprint, current_app, request

from app.core.errors import not_found, unauthorized
from app.core.responses import ok
from app.models.base import utcnow

bp = Blueprint("internal", __name__, url_prefix="/api/v1/internal")


@bp.post("/run-jobs")
def run_jobs():
    token = current_app.config.get("JOBS_TOKEN") or ""
    if not token:
        raise not_found("Endpoint")
    if not hmac.compare_digest(request.headers.get("X-Jobs-Token", ""), token):
        raise unauthorized("Invalid token", "invalid_token")
    from app.jobs import tasks

    fns = [tasks.billing_lifecycle, tasks.resume_automations, tasks.send_scheduled_emails, tasks.send_reminders, tasks.send_scheduled_reports, tasks.release_expired_holds]
    if utcnow().hour == 3:
        fns.append(tasks.housekeeping)
    results = {}
    for fn in fns:
        try:
            results[fn.name] = fn()
        except Exception as e:  # one failing job must not block the others; the job wrapper already logged it
            results[fn.name] = {"error": str(e)[:200]}
    return ok(results)
