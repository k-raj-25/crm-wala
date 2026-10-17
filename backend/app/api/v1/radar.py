"""Lead leakage radar (owner and admins only): see app.services.leakage."""
from __future__ import annotations

from flask import Blueprint, g, request

from app.core.auth import protect, require
from app.core.errors import bad_request
from app.core.responses import ok
from app.extensions import db
from app.schemas.common import Schema, parse
from app.services import audit, leakage, privacy

bp = Blueprint("radar", __name__, url_prefix="/api/v1/radar")
bp.after_request(privacy.mask_response)  # lost reasons are free text and could carry a number

PERIODS = {7, 30, 90}


def _settings() -> dict:
    s = g.workspace.settings or {}
    return {"weekly_report": leakage.weekly_enabled(g.workspace), "last_sent_at": s.get("leakage_report_sent_at")}


@bp.get("")
@protect("audit.read")
def radar():
    days = request.args.get("days", "7")
    if not days.isdigit() or int(days) not in PERIODS:
        raise bad_request("days must be 7, 30 or 90")
    return ok({**leakage.run(g.workspace.id, int(days)), "settings": _settings()})


class RadarSettingsIn(Schema):
    weekly_report: bool


@bp.put("/settings")
@protect("audit.read")
def update_settings():
    require("settings.manage")
    d = parse(RadarSettingsIn)
    g.workspace.settings = {**(g.workspace.settings or {}), "leakage_report": d.weekly_report}
    audit.record("workspace.leakage_report", entity_type="workspace", entity_id=g.workspace.id,
                 summary="Weekly lead leakage report turned on" if d.weekly_report else "Weekly lead leakage report turned off", after={"leakage_report": d.weekly_report})
    db.session.commit()
    return ok(_settings())
