"""Domain events. Today they feed the automation engine; the seam is intentionally tiny."""
from __future__ import annotations

import logging

from flask import g

log = logging.getLogger("app.events")


def emit(trigger: str, payload: dict, *, workspace_id=None) -> None:
    from app.services.automation import dispatch

    from app.services.integrations import publish

    wid = workspace_id or g.workspace.id
    try:
        dispatch(wid, trigger, payload)
    except Exception:  # automations must never break the user's action
        log.exception("automation dispatch failed for %s", trigger)
    try:
        publish(wid, trigger, payload)
        if trigger == "deal.stage_changed" and payload.get("stage_kind") in ("won", "lost"):
            publish(wid, f"deal.{payload['stage_kind']}", payload)
    except Exception:
        log.exception("outbound publish failed for %s", trigger)
