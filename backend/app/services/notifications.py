from __future__ import annotations

from typing import Iterable

from flask import current_app

from app.extensions import db
from app.models import Notification, User, WorkspaceMember
from app.services import email as email_service

NOTIFICATION_TYPES = {
    "new_lead": "New lead", "task_assigned": "Assigned task", "deal_update": "Deal update", "mention": "Mention",
    "meeting_reminder": "Meeting reminder", "automation": "Automation result", "payment_issue": "Payment issue",
    "trial_ending": "Trial ending", "system": "System notification",
}
# Defaults when a member hasn't customised preferences: in-app on, email only for important ones.
DEFAULT_PREFS = {t: {"in_app": True, "email": t in {"payment_issue", "trial_ending", "mention", "task_assigned"}} for t in NOTIFICATION_TYPES}


def prefs_for(member: WorkspaceMember | None, ntype: str) -> dict:
    base = DEFAULT_PREFS.get(ntype, {"in_app": True, "email": False})
    if member is None:
        return base
    return {**base, **(member.notification_prefs or {}).get(ntype, {})}


def notify(workspace_id, user_ids: Iterable, ntype: str, title: str, body: str | None = None, link: str | None = None,
           data: dict | None = None, *, exclude_user_id=None) -> int:
    count = 0
    for uid in {u for u in user_ids if u and u != exclude_user_id}:
        member = db.session.query(WorkspaceMember).filter_by(workspace_id=workspace_id, user_id=uid, status="active").one_or_none()
        if member is None:
            continue
        p = prefs_for(member, ntype)
        if p.get("in_app", True):
            db.session.add(Notification(workspace_id=workspace_id, user_id=uid, type=ntype, title=title[:200],
                                        body=(body or "")[:500] or None, link=link, data=data or {}))
            count += 1
        if p.get("email"):
            user = db.session.get(User, uid)
            if user:
                html = f"<h1>{title}</h1><p>{body or ''}</p>"
                if link:
                    html += f"<p><a class='btn' href='{current_app.config['WEB_ORIGIN']}{link}'>Open in CRM</a></p>"
                subject, full = title, email_service.LAYOUT.replace("{{ content }}", html)
                email_service.send_raw(user.email, subject, full, workspace_id=workspace_id, template_key=f"notification.{ntype}")
    return count


def workspace_admins(workspace_id) -> list:
    from app.models import Role

    rows = (
        db.session.query(WorkspaceMember.user_id).join(Role, Role.id == WorkspaceMember.role_id)
        .filter(WorkspaceMember.workspace_id == workspace_id, Role.key.in_(("owner", "admin")), WorkspaceMember.status == "active").all()
    )
    return [r[0] for r in rows]
