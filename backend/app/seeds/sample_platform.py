"""Synthetic customer base so the Super Admin dashboards have something to show in development.

Every row is tagged: users are @sample.crmwala.dev and workspaces have slug "sample-*", so `--reset` removes exactly these
and nothing else. Never run against production (the CLI refuses)."""
from __future__ import annotations

import datetime as dt
import random

from app.core.passwords import hash_password
from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import AnalyticsEvent, AuditLog, JobLog, Payment, Plan, Subscription, User, UserActivityDay, Workspace, WorkspaceMember
from app.models.base import utcnow
from app.services.workspaces import create_workspace, seed_platform

NAMES = ["Northwind Traders", "Kestrel Labs", "Maple Street Realty", "Indigo Interiors", "Pulse Fitness", "Redwood Advisors", "Skyline Travel", "Tandoor Tales", "Vega Motors", "Willow Dental",
         "Yamuna Exports", "Zephyr Studios", "Aurora Solar", "Banyan Learning", "Cedar Legal", "Delta Couriers", "Ember Coffee", "Falcon Security", "Glow Skincare", "Helix Biotech",
         "Ivory Events", "Juniper Homes", "Kite Marketing", "Lotus Wellness", "Mosaic Tiles", "Nova Fintech", "Opal Jewellers", "Prism Photography"]
PLANS = ["starter", "starter", "growth", "growth", "growth", "business"]
SLUG_PREFIX = "sample-"


def reset() -> int:
    with bypass_scope():
        ids = [w.id for w in db.session.query(Workspace).filter(Workspace.slug.like(f"{SLUG_PREFIX}%"))]
        for t in (AnalyticsEvent, UserActivityDay, Payment, Subscription, AuditLog):
            if ids:
                db.session.query(t).filter(t.workspace_id.in_(ids)).delete(synchronize_session=False)
        owners = [w.owner_id for w in db.session.query(Workspace).filter(Workspace.id.in_(ids))] if ids else []
        for wid in ids:
            db.session.delete(db.session.get(Workspace, wid))
        db.session.flush()
        db.session.query(WorkspaceMember).filter(WorkspaceMember.user_id.in_(owners)).delete(synchronize_session=False)
        db.session.query(User).filter(User.email.like("%@sample.crmwala.dev")).delete(synchronize_session=False)
        db.session.commit()
        return len(ids)


def seed(count: int = 28, seed_value: int = 7) -> dict:
    rnd = random.Random(seed_value)
    now = utcnow()
    made = {"workspaces": 0, "payments": 0}
    with bypass_scope():
        seed_platform()
        reset()
        plans = {p.key: p for p in db.session.query(Plan)}
        pw = hash_password("Sample@12345")
        for i in range(min(count, len(NAMES))):
            name = NAMES[i]
            age = rnd.randint(2, 88)  # days since signup
            created = now - dt.timedelta(days=age, hours=rnd.randint(0, 20))
            owner = User(name=f"{name.split()[0]} Owner", email=f"owner{i + 1}@sample.crmwala.dev", password_hash=pw, email_verified_at=created, created_at=created,
                         last_login_at=now - dt.timedelta(days=rnd.randint(0, min(age, 20))))
            db.session.add(owner)
            db.session.flush()
            ws = create_workspace(owner, name, company_size=rnd.choice(["1-10", "11-50", "51-200"]), industry=rnd.choice(["SaaS", "Retail", "Services", "Health", "Education"]))
            ws.slug = f"{SLUG_PREFIX}{i + 1}-{ws.slug[:30]}"
            ws.created_at = created
            ws.trial_started_at = created
            ws.trial_ends_at = created + dt.timedelta(days=3)
            ws.onboarding_completed_at = created + dt.timedelta(minutes=rnd.randint(5, 40))
            ws.last_activity_at = now - dt.timedelta(days=rnd.randint(0, 10))
            outcome = "trial" if age <= 3 else rnd.choices(["paid", "expired", "canceled", "past_due"], [58, 24, 10, 8])[0]
            if outcome == "trial":
                pass
            elif outcome == "expired":
                ws.plan_key, ws.subscription_status = "trial", "expired"
            else:
                key = rnd.choice(PLANS)
                plan = plans[key]
                interval = rnd.choice(["monthly", "monthly", "annual"])
                amount = (plan.price_annual if interval == "annual" else plan.price_monthly) or 0
                start = created + dt.timedelta(days=rnd.randint(1, 3))
                ws.plan_key, ws.billing_interval = key, interval
                ws.subscription_status = {"paid": "active", "canceled": "canceled", "past_due": "past_due"}[outcome]
                ws.current_period_end = now + dt.timedelta(days=rnd.randint(2, 28))
                if outcome == "past_due":
                    ws.grace_ends_at = now + dt.timedelta(days=2)
                sub = Subscription(workspace_id=ws.id, plan_key=key, interval=interval, status="ended" if outcome == "canceled" else ("past_due" if outcome == "past_due" else "active"),
                                   amount=amount, currency="INR", provider="mock", current_period_start=start, current_period_end=ws.current_period_end, created_at=start,
                                   cancel_at_period_end=False, ended_at=now - dt.timedelta(days=rnd.randint(1, 20)) if outcome == "canceled" else None)
                db.session.add(sub)
                db.session.flush()
                d = start
                while d < now and (interval == "monthly" or d == start):
                    db.session.add(Payment(workspace_id=ws.id, subscription_id=sub.id, amount=amount, currency="INR", status="succeeded", provider="mock", created_at=d,
                                           description=f"{plan.name} · {interval}"))
                    made["payments"] += 1
                    d += dt.timedelta(days=30)
                if outcome == "past_due":
                    db.session.add(Payment(workspace_id=ws.id, subscription_id=sub.id, amount=amount, currency="INR", status="failed", provider="mock", created_at=now - dt.timedelta(days=1),
                                           description=f"{plan.name} · {interval}", failure_reason="Card declined by issuer"))
            # funnel + activity
            for ev, delay in (("signup", 0), ("workspace_created", 0), ("onboarding_completed", 1), ("lead_created", 2), ("deal_created", 3)):
                if ev in ("lead_created", "deal_created") and rnd.random() < (0.35 if outcome == "expired" else 0.1):
                    continue
                if ev == "onboarding_completed" and rnd.random() < 0.1:
                    continue
                db.session.add(AnalyticsEvent(name=ev, workspace_id=ws.id, user_id=owner.id, created_at=created + dt.timedelta(days=delay)))
            if outcome == "paid":
                for ev in ("deal_won", "subscription_started", "ai_chat", "automation_created"):
                    if rnd.random() < 0.6:
                        db.session.add(AnalyticsEvent(name=ev, workspace_id=ws.id, user_id=owner.id, created_at=now - dt.timedelta(days=rnd.randint(0, age))))
            if outcome in ("paid", "past_due", "trial"):
                for back in range(min(age, 40)):
                    if rnd.random() < (0.7 if outcome == "paid" else 0.4):
                        db.session.add(UserActivityDay(user_id=owner.id, day=(now - dt.timedelta(days=back)).date(), workspace_id=ws.id))
                for _ in range(rnd.randint(3, 25)):
                    db.session.add(AuditLog(workspace_id=ws.id, actor_type="user", actor_id=owner.id, actor_label=owner.email, action="lead.create",
                                            entity_type=rnd.choice(["lead", "deal", "contact", "task", "company"]), summary="Created record",
                                            created_at=now - dt.timedelta(days=rnd.randint(0, min(age, 30)))))
            made["workspaces"] += 1
        for n, name in enumerate(("billing_lifecycle", "resume_automations", "send_scheduled_emails", "send_reminders", "housekeeping")):
            for k in range(4):
                db.session.add(JobLog(name=name, status="success", duration_ms=rnd.randint(12, 480), created_at=now - dt.timedelta(minutes=5 * (n + k * 5))))
        db.session.commit()
    return made
