"""Celery application. Tasks run inside a Flask app context; set CELERY_ALWAYS_EAGER=true to run them inline (dev/tests)."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import Config

celery = Celery("crm", broker=Config.REDIS_URL, backend=Config.REDIS_URL, include=["app.jobs.tasks"])
celery.conf.update(
    task_always_eager=Config.CELERY_ALWAYS_EAGER, task_serializer="json", result_expires=3600, timezone="UTC", task_acks_late=True,
    worker_prefetch_multiplier=1, task_time_limit=300,
    beat_schedule={
        "billing-lifecycle": {"task": "jobs.billing_lifecycle", "schedule": crontab(minute="*/10")},
        "resume-automations": {"task": "jobs.resume_automations", "schedule": crontab(minute="*")},
        "send-scheduled-emails": {"task": "jobs.send_scheduled_emails", "schedule": crontab(minute="*")},
        "reminders": {"task": "jobs.send_reminders", "schedule": crontab(minute="*/5")},
        "scheduled-reports": {"task": "jobs.send_scheduled_reports", "schedule": crontab(minute=5, hour="*")},
        "housekeeping": {"task": "jobs.housekeeping", "schedule": crontab(minute=30, hour=3)},
    },
)
