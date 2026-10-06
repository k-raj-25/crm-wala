from __future__ import annotations

import logging

from flask import g, has_request_context

from app.extensions import db
from app.models import AnalyticsEvent

log = logging.getLogger("app.analytics")


def track(name: str, properties: dict | None = None, *, workspace_id=None, user_id=None) -> None:
    """Product analytics event (signup, lead_created, ...). Never raises into the request path."""
    try:
        if has_request_context():
            workspace_id = workspace_id or getattr(getattr(g, "workspace", None), "id", None)
            user_id = user_id or getattr(getattr(g, "user", None), "id", None)
        db.session.add(AnalyticsEvent(name=name, workspace_id=workspace_id, user_id=user_id, properties=properties or {}))
    except Exception:  # pragma: no cover
        log.exception("analytics track failed")
