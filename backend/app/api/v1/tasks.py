from __future__ import annotations

import datetime as dt

from flask import Blueprint, g, request
from sqlalchemy import func

from app.core import search_expr
from app.core.auth import protect
from app.core.crud import CrudResource
from app.core.responses import ok
from app.extensions import db
from app.models import Company, Contact, Deal, Lead, Task
from app.models.base import utcnow
from app.schemas.crm import TaskIn, TaskPatch
from app.services import activities, events, notifications
from app.services.related import attach_related

bp = Blueprint("tasks", __name__, url_prefix="/api/v1/tasks")


def _day_bounds():
    now = utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return now, start, start + dt.timedelta(days=1)


class TaskResource(CrudResource):
    name, entity_type, model = "tasks", "task", Task
    create_schema, patch_schema = TaskIn, TaskPatch
    owner_field = "assignee_id"
    search_cols = [search_expr.TASKS]
    sort_fields = {"created_at": Task.created_at, "due_at": Task.due_at, "priority": Task.priority, "status": Task.status, "title": Task.title, "position": Task.position}
    default_sort = "due_at"
    filters = {
        "status": ("in", Task.status), "assignee_id": ("in", Task.assignee_id), "priority": ("in", Task.priority), "kind": ("in", Task.kind),
        "due_at": ("date", Task.due_at), "lead_id": ("eq", Task.lead_id), "contact_id": ("eq", Task.contact_id),
        "company_id": ("eq", Task.company_id), "deal_id": ("eq", Task.deal_id),
    }
    refs = {"assignee_id": "member", "lead_id": Lead, "contact_id": Contact, "company_id": Company, "deal_id": Deal}
    export_columns = [
        ("Title", lambda o: o.title), ("Status", lambda o: o.status), ("Priority", lambda o: o.priority), ("Due", lambda o: o.due_at.isoformat() if o.due_at else ""),
        ("Assignee", lambda o: o._owner_name), ("Description", lambda o: o.description),
    ]

    def extra_filters(self, q):
        now, start, end = _day_bounds()
        view = request.args.get("view")
        open_ = Task.status != "completed"
        if view == "today":
            q = q.where(open_, Task.due_at >= start, Task.due_at < end)
        elif view == "overdue":
            q = q.where(open_, Task.due_at < start)
        elif view == "upcoming":
            q = q.where(open_, Task.due_at >= end)
        elif view == "no_date":
            q = q.where(open_, Task.due_at.is_(None))
        elif view == "open":
            q = q.where(open_)
        return q

    def default_sort_override(self):
        return None

    def serialize_many(self, objs):
        out = super().serialize_many(objs)
        for d in out:
            d["assignee"] = d.pop("owner")
        attach_related(objs, out)
        return out

    def label(self, o):
        return o.title

    def prepare_create(self, data):
        data["assignee_id"] = data.get("assignee_id") or g.user.id
        data["created_by"] = g.user.id
        if data["status"] == "completed":
            data["completed_at"] = utcnow()
        return data

    def after_create(self, t, data):
        activities.log_activity("task", f"Task created: {t.title}", lead_id=t.lead_id, contact_id=t.contact_id, company_id=t.company_id,
                                deal_id=t.deal_id, data={"task_id": str(t.id)})
        if t.assignee_id != g.user.id:
            notifications.notify(g.workspace.id, [t.assignee_id], "task_assigned", f"New task: {t.title}", f"{g.user.name} assigned you a task.",
                                 "/app/tasks", exclude_user_id=g.user.id)

    def prepare_update(self, t, changes):
        if "status" in changes:
            if changes["status"] == "completed" and t.status != "completed":
                changes["completed_at"] = utcnow()
            elif changes["status"] != "completed":
                changes["completed_at"] = None
        if "due_at" in changes:
            changes["reminder_sent_at"] = None
        return changes

    def after_update(self, t, before, changes):
        if "status" in changes and before["status"] != "completed" and t.status == "completed":
            activities.log_activity("task_completed", f"Task completed: {t.title}", lead_id=t.lead_id, contact_id=t.contact_id,
                                    company_id=t.company_id, deal_id=t.deal_id, data={"task_id": str(t.id)})
            events.emit("task.completed", {"task_id": str(t.id), "title": t.title, "assignee_id": str(t.assignee_id) if t.assignee_id else None})
        if "assignee_id" in changes and t.assignee_id and before["assignee_id"] != str(t.assignee_id):
            notifications.notify(g.workspace.id, [t.assignee_id], "task_assigned", f"Task assigned: {t.title}", f"{g.user.name} assigned you a task.",
                                 "/app/tasks", exclude_user_id=g.user.id)


res = TaskResource()
res.register(bp)


@bp.get("/summary")
@protect("tasks.read")
def summary():
    now, start, end = _day_bounds()
    base = db.session.query(Task).filter(Task.workspace_id == g.workspace.id, Task.deleted_at.is_(None))
    if request.args.get("mine") == "true":
        base = base.filter(Task.assignee_id == g.user.id)
    open_ = base.filter(Task.status != "completed")
    return ok({
        "today": open_.filter(Task.due_at >= start, Task.due_at < end).count(),
        "overdue": open_.filter(Task.due_at < start).count(),
        "upcoming": open_.filter(Task.due_at >= end).count(),
        "no_date": open_.filter(Task.due_at.is_(None)).count(),
        "completed": base.filter(Task.status == "completed").count(),
    })
