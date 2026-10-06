"""Automation engine: trigger -> linear chain of actions (with delays). Runs are persisted so delays survive restarts.

Design notes
- Actions never emit domain events themselves, so automations cannot trigger each other in loops.
- Workflows are validated (single trigger, acyclic chain, known node types) before they can be saved.
- Webhook actions refuse private/loopback addresses (SSRF protection).
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import logging
import socket
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import func

from app.core.errors import ApiError
from app.extensions import db
from app.models import (
    Activity, Automation, AutomationRun, Contact, Deal, Lead, PipelineStage, Role, Task, User, WorkspaceMember,
)
from app.models.base import utcnow

log = logging.getLogger("app.automation")

TRIGGERS = {
    "lead.created": {"label": "Lead created", "config": []},
    "deal.created": {"label": "Deal created", "config": []},
    "deal.stage_changed": {"label": "Deal stage changed", "config": [{"key": "stage", "label": "Only when moved to stage", "type": "text"}]},
    "task.completed": {"label": "Task completed", "config": []},
    "contact.updated": {"label": "Contact updated", "config": []},
    "form.submitted": {"label": "Form submitted", "config": []},
    "trial.ending": {"label": "Trial ending", "config": []},
    "payment.failed": {"label": "Payment failed", "config": []},
}
ACTIONS = {
    "send_email": {"label": "Send email", "fields": [{"key": "to", "label": "To", "type": "select", "options": ["record", "owner"], "default": "record"},
                                                     {"key": "subject", "label": "Subject", "type": "text"}, {"key": "body", "label": "Message", "type": "textarea"}]},
    "create_task": {"label": "Create task", "fields": [{"key": "title", "label": "Task title", "type": "text"}, {"key": "due_in_days", "label": "Due in (days)", "type": "number", "default": 1},
                                                      {"key": "priority", "label": "Priority", "type": "select", "options": ["low", "medium", "high", "urgent"], "default": "medium"}]},
    "assign_user": {"label": "Assign user", "fields": [{"key": "strategy", "label": "Strategy", "type": "select", "options": ["round_robin", "user"], "default": "round_robin"},
                                                       {"key": "user_id", "label": "User", "type": "user"}]},
    "add_tag": {"label": "Add tag", "fields": [{"key": "tag", "label": "Tag", "type": "text"}]},
    "change_status": {"label": "Change status", "fields": [{"key": "value", "label": "Lead status or deal stage name", "type": "text"}]},
    "send_notification": {"label": "Send notification", "fields": [{"key": "title", "label": "Title", "type": "text"}, {"key": "body", "label": "Message", "type": "text"},
                                                                {"key": "to", "label": "Notify", "type": "select", "options": ["owner", "admins"], "default": "owner"}]},
    "webhook": {"label": "Webhook", "fields": [{"key": "url", "label": "URL", "type": "text"}]},
    "delay": {"label": "Wait", "fields": [{"key": "amount", "label": "Amount", "type": "number", "default": 1},
                                         {"key": "unit", "label": "Unit", "type": "select", "options": ["minutes", "hours", "days"], "default": "days"}]},
    "create_activity": {"label": "Create activity", "fields": [{"key": "title", "label": "Activity title", "type": "text"}]},
}
MAX_NODES = 20


def validate_graph(graph: dict, trigger_type: str) -> None:
    nodes, edges = graph.get("nodes") or [], graph.get("edges") or []
    if not nodes or len(nodes) > MAX_NODES:
        raise ApiError(422, "validation_error", f"A workflow needs between 1 and {MAX_NODES} steps", {"graph": "Invalid size"})
    ids = {n.get("id") for n in nodes}
    if len(ids) != len(nodes):
        raise ApiError(422, "validation_error", "Duplicate step ids", {"graph": "Duplicate ids"})
    triggers = [n for n in nodes if n.get("type") == "trigger"]
    if len(triggers) != 1:
        raise ApiError(422, "validation_error", "A workflow needs exactly one trigger", {"graph": "One trigger required"})
    if triggers[0].get("data", {}).get("trigger_type") != trigger_type:
        raise ApiError(422, "validation_error", "Trigger node doesn't match the workflow trigger", {"graph": "Trigger mismatch"})
    for n in nodes:
        if n.get("type") == "action":
            at = n.get("data", {}).get("action_type")
            if at not in ACTIONS:
                raise ApiError(422, "validation_error", f"Unknown action “{at}”", {"graph": "Unknown action"})
            if at == "delay":
                amt = n["data"].get("config", {}).get("amount")
                if not isinstance(amt, (int, float)) or amt <= 0 or amt > 365:
                    raise ApiError(422, "validation_error", "Wait time must be between 1 and 365", {"graph": "Invalid delay"})
        elif n.get("type") != "trigger":
            raise ApiError(422, "validation_error", "Unknown step type", {"graph": "Unknown type"})
    nxt: dict[str, str] = {}
    for e in edges:
        if e.get("source") not in ids or e.get("target") not in ids:
            raise ApiError(422, "validation_error", "Connection points to a missing step", {"graph": "Bad edge"})
        if e["source"] in nxt:
            raise ApiError(422, "validation_error", "Each step can only connect to one next step", {"graph": "Branching not supported"})
        nxt[e["source"]] = e["target"]
    seen, cur = set(), triggers[0]["id"]
    while cur in nxt:
        if cur in seen:
            raise ApiError(422, "validation_error", "Workflow contains a loop", {"graph": "Cycle"})
        seen.add(cur)
        cur = nxt[cur]


def _chain(graph: dict) -> list[dict]:
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    nxt = {e["source"]: e["target"] for e in graph.get("edges", [])}
    start = next((n["id"] for n in nodes.values() if n.get("type") == "trigger"), None)
    out, cur = [], start
    while cur is not None:
        out.append(nodes[cur])
        cur = nxt.get(cur)
    return out


def safe_url(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def dispatch(workspace_id, trigger: str, payload: dict) -> int:
    autos = db.session.query(Automation).filter(Automation.workspace_id == workspace_id, Automation.is_active.is_(True), Automation.deleted_at.is_(None),
                                                Automation.trigger_type == trigger).all()
    n = 0
    for a in autos:
        stage = (a.trigger_config or {}).get("stage")
        if trigger == "deal.stage_changed" and stage and stage.lower() != str(payload.get("stage", "")).lower():
            continue
        run = AutomationRun(workspace_id=workspace_id, automation_id=a.id, status="running", trigger_payload=payload, steps=[])
        db.session.add(run)
        a.run_count += 1
        a.last_run_at = utcnow()
        db.session.flush()
        execute(run, a)
        n += 1
    return n


def _record(model, payload_key: str, payload: dict, ws):
    rid = payload.get(payload_key)
    return db.session.query(model).filter(model.id == rid, model.workspace_id == ws).first() if rid else None


def _target_record(payload: dict, ws):
    """The CRM record the automation is about, plus its owner and email."""
    for key, model in (("lead_id", Lead), ("deal_id", Deal), ("contact_id", Contact)):
        rec = _record(model, key, payload, ws)
        if rec is not None:
            return rec
    return None


def execute(run: AutomationRun, automation: Automation | None = None, *, dry_run: bool = False) -> AutomationRun:
    ws = run.workspace_id
    automation = automation or db.session.get(Automation, run.automation_id)
    chain = _chain(automation.graph)
    start_idx = 1
    if run.cursor_node_id:
        start_idx = next((i for i, n in enumerate(chain) if n["id"] == run.cursor_node_id), len(chain))
    steps = list(run.steps or [])
    run.status, run.resume_at, run.cursor_node_id = "running", None, None
    for node in chain[start_idx:]:
        data = node.get("data", {})
        at, cfg = data.get("action_type"), data.get("config", {})
        try:
            if at == "delay":
                secs = {"minutes": 60, "hours": 3600, "days": 86400}[cfg.get("unit", "days")] * float(cfg.get("amount", 1))
                idx = chain.index(node)
                steps.append({"node_id": node["id"], "type": at, "status": "waiting", "detail": f"Waiting {cfg.get('amount')} {cfg.get('unit')}", "at": utcnow().isoformat()})
                if idx + 1 >= len(chain):
                    break
                run.cursor_node_id = chain[idx + 1]["id"]
                run.resume_at = utcnow() + dt.timedelta(seconds=secs)
                run.status = "waiting"
                if dry_run:
                    run.status, run.cursor_node_id = "completed", None
                    continue
                run.steps = steps
                return run
            detail = "Skipped (dry run)" if dry_run else _perform(at, cfg, run, ws)
            steps.append({"node_id": node["id"], "type": at, "status": "done", "detail": detail, "at": utcnow().isoformat()})
        except Exception as e:  # one failing step fails the run but never the request
            log.exception("automation step failed")
            steps.append({"node_id": node["id"], "type": at, "status": "failed", "detail": str(e)[:300], "at": utcnow().isoformat()})
            run.status, run.error, run.finished_at, run.steps = "failed", str(e)[:500], utcnow(), steps
            return run
    run.status, run.finished_at, run.steps = "completed", utcnow(), steps
    return run


def resume_due(limit: int = 200) -> int:
    from app.core.tenant import bypass_scope, tenant_scope

    n = 0
    with bypass_scope():
        due = db.session.query(AutomationRun).filter(AutomationRun.status == "waiting", AutomationRun.resume_at <= utcnow()).order_by(AutomationRun.resume_at).limit(limit).all()
        refs = [(r.id, r.workspace_id) for r in due]
    for rid, wid in refs:
        with tenant_scope(wid):
            run = db.session.get(AutomationRun, rid)
            if run and run.status == "waiting":
                execute(run)
                n += 1
            db.session.commit()
    return n


# ---- actions ------------------------------------------------------------------------------

def _fmt(text: str, rec, payload: dict) -> str:
    ctx = {"name": payload.get("name") or getattr(rec, "name", "") or "", "first_name": getattr(rec, "first_name", "") or "", "stage": payload.get("stage", ""),
           "value": payload.get("value", ""), "title": payload.get("title", "")}
    for k, v in ctx.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def _perform(action: str, cfg: dict, run: AutomationRun, ws) -> str:
    payload = run.trigger_payload or {}
    rec = _target_record(payload, ws)
    owner_id = getattr(rec, "owner_id", None) or (payload.get("owner_id") and uuid.UUID(payload["owner_id"])) or None
    if action == "create_task":
        t = Task(workspace_id=ws, title=_fmt(cfg.get("title") or "Follow up", rec, payload)[:240], assignee_id=owner_id, kind="follow_up", priority=cfg.get("priority", "medium"),
                 due_at=utcnow() + dt.timedelta(days=float(cfg.get("due_in_days", 1))), lead_id=getattr(rec, "id", None) if isinstance(rec, Lead) else None,
                 deal_id=rec.id if isinstance(rec, Deal) else None, contact_id=rec.id if isinstance(rec, Contact) else None)
        db.session.add(t)
        return f"Created task “{t.title}”"
    if action == "send_email":
        from app.services import email as email_service

        to = None
        if cfg.get("to") == "owner" and owner_id:
            u = db.session.get(User, owner_id)
            to = u.email if u else None
        elif rec is not None:
            to = getattr(rec, "email", None) or (rec.contact.email if isinstance(rec, Deal) and rec.contact else None)
        if not to:
            return "Skipped: no recipient email"
        subject, body = _fmt(cfg.get("subject") or "Hello", rec, payload), _fmt(cfg.get("body") or "", rec, payload)
        from app.services.mailbox import text_to_html

        email_service.send_raw(to, subject, text_to_html(body), workspace_id=ws, template_key="automation")
        return f"Sent email to {to}"
    if action == "assign_user":
        uid = None
        if cfg.get("strategy") == "user" and cfg.get("user_id"):
            uid = uuid.UUID(cfg["user_id"])
            if not db.session.query(WorkspaceMember.id).filter_by(workspace_id=ws, user_id=uid, status="active").first():
                raise ValueError("Selected user is no longer in the workspace")
        else:
            members = [m for (m,) in db.session.query(WorkspaceMember.user_id).join(Role, Role.id == WorkspaceMember.role_id).filter(
                WorkspaceMember.workspace_id == ws, WorkspaceMember.status == "active", Role.rank >= 40, Role.key != "viewer")]
            if not members:
                return "Skipped: no eligible users"
            load = dict(db.session.query(Lead.owner_id, func.count()).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.status.in_(("new", "contacted", "qualified")),
                                                                             Lead.owner_id.in_(members)).group_by(Lead.owner_id).all())
            uid = min(members, key=lambda m: load.get(m, 0))
        if rec is None or not hasattr(rec, "owner_id"):
            return "Skipped: nothing to assign"
        rec.owner_id = uid
        from app.services.notifications import notify

        notify(ws, [uid], "task_assigned", f"Assigned to you: {getattr(rec, 'name', 'record')}", "An automation assigned this to you.",
               f"/app/{'leads' if isinstance(rec, Lead) else 'deals' if isinstance(rec, Deal) else 'contacts'}/{rec.id}")
        u = db.session.get(User, uid)
        return f"Assigned to {u.name if u else uid}"
    if action == "add_tag":
        tag = (cfg.get("tag") or "").strip()[:40]
        if rec is None or not tag or not hasattr(rec, "tags"):
            return "Skipped"
        rec.tags = sorted(set(rec.tags or []) | {tag})
        from app.models import Tag

        if not db.session.query(Tag).filter_by(workspace_id=ws, name=tag).first():
            db.session.add(Tag(workspace_id=ws, name=tag, color="#6366f1"))
        return f"Added tag “{tag}”"
    if action == "change_status":
        value = (cfg.get("value") or "").strip()
        if isinstance(rec, Lead):
            from app.models import Workspace

            keys = [s["key"] for s in (db.session.get(Workspace, ws).settings or {}).get("lead_statuses", [])]
            if value.lower() not in keys or value.lower() == "converted":
                raise ValueError(f"Invalid lead status “{value}”")
            rec.status = value.lower()
            return f"Lead status → {value.lower()}"
        if isinstance(rec, Deal):
            st = db.session.query(PipelineStage).filter(PipelineStage.pipeline_id == rec.pipeline_id, func.lower(PipelineStage.name) == value.lower()).first()
            if st is None:
                raise ValueError(f"No stage named “{value}”")
            from app.api.v1.deals import apply_stage

            apply_stage(rec, st)
            return f"Deal stage → {st.name}"
        return "Skipped: nothing to change"
    if action == "send_notification":
        from app.services.notifications import notify, workspace_admins

        targets = workspace_admins(ws) if cfg.get("to") == "admins" else [owner_id]
        n = notify(ws, targets, "automation", _fmt(cfg.get("title") or "Automation", rec, payload), _fmt(cfg.get("body") or "", rec, payload), None)
        return f"Notified {n} user(s)"
    if action == "webhook":
        url = cfg.get("url", "")
        if not safe_url(url):
            raise ValueError("Webhook URL must be a public http(s) address")
        r = httpx.post(url, json={"event": run.trigger_payload, "automation_run_id": str(run.id)}, timeout=5, follow_redirects=False)
        return f"POST {urlparse(url).netloc} → {r.status_code}"
    if action == "create_activity":
        db.session.add(Activity(workspace_id=ws, type="system", title=_fmt(cfg.get("title") or "Automation ran", rec, payload)[:300],
                                lead_id=rec.id if isinstance(rec, Lead) else None, deal_id=rec.id if isinstance(rec, Deal) else None,
                                contact_id=rec.id if isinstance(rec, Contact) else None, occurred_at=utcnow()))
        return "Activity created"
    raise ValueError(f"Unknown action {action}")
