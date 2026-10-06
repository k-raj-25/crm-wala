from __future__ import annotations

import logging
from typing import Any

from flask import g, has_request_context, request

from app.extensions import db
from app.models import AuditLog
from app.models.base import _jsonable

log = logging.getLogger("app.audit")


def record(
    action: str, *, entity_type: str | None = None, entity_id: Any = None, summary: str | None = None,
    before: dict | None = None, after: dict | None = None, workspace_id: Any = None,
    actor_type: str | None = None, actor_id: Any = None, actor_label: str | None = None,
) -> AuditLog:
    """Append an audit row inside the caller's transaction (so it commits/rolls back with the change)."""
    ip = ua = None
    impersonator = None
    if has_request_context():
        ip = request.remote_addr
        ua = (request.headers.get("User-Agent") or "")[:300]
        admin = getattr(g, "admin", None)
        user = getattr(g, "user", None)
        if actor_type is None:
            if admin is not None:
                actor_type, actor_id, actor_label = "admin", admin.id, admin.email
            elif user is not None:
                actor_type, actor_id, actor_label = "user", user.id, user.name
                impersonator = getattr(g, "impersonator_id", None)
        if workspace_id is None and getattr(g, "workspace", None) is not None:
            workspace_id = g.workspace.id
    row = AuditLog(
        workspace_id=workspace_id, actor_type=actor_type or "system", actor_id=actor_id, actor_label=actor_label,
        impersonator_id=impersonator, action=action, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None, summary=summary,
        before=_jsonable(before) if before else None, after=_jsonable(after) if after else None, ip=ip, user_agent=ua,
    )
    db.session.add(row)
    return row


def diff(before: dict, after: dict, ignore: tuple[str, ...] = ("updated_at",)) -> tuple[dict, dict]:
    b, a = {}, {}
    for k in after:
        if k in ignore:
            continue
        if before.get(k) != after.get(k):
            b[k], a[k] = before.get(k), after.get(k)
    return b, a
