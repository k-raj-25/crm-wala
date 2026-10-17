"""The CRM inside WhatsApp: each rep links their own number and picks what arrives on WhatsApp; admins pick the alert template."""
from __future__ import annotations

from urllib.parse import quote

from flask import Blueprint, g
from pydantic import Field

from app.core.auth import protect
from app.core.errors import ApiError
from app.core.permissions import has_permission
from app.core.responses import ok
from app.extensions import db
from app.schemas.common import Schema, parse
from app.models.base import utcnow
from app.services import integrations, whatsapp as wa, whatsapp_crm as svc

bp = Blueprint("whatsapp_crm", __name__, url_prefix="/api/v1/whatsapp")


def _connected():
    i = integrations.get(g.workspace.id, "whatsapp")
    return i if i and i.status in ("connected", "error") and i.credentials_enc else None


def _view() -> dict:
    i = _connected()
    p = svc.prefs(g.member)
    number = svc.company_number(i)
    code = p.get("code") if p.get("code_expires_at") and p["code_expires_at"] > utcnow().isoformat() else None
    missing = [f for f in ("whatsapp_integration", "ai_assistant") if f not in g.features]
    reason = ("Your workspace hasn't connected WhatsApp yet. An admin can connect it in Integrations." if not i else
              "The CRM on WhatsApp needs the WhatsApp and AI assistant features on your plan." if missing else
              "Your role doesn't include the AI assistant." if not has_permission(g.permissions, "ai.use") else None)
    return {
        "available": reason is None, "reason": reason, "company_number": number and f"+{number}",
        "profile_phone": wa.normalize_phone(g.user.phone) and f"+{wa.normalize_phone(g.user.phone)}",
        "linked": bool(svc.linked_phone(g.member, g.user)), "linked_at": p.get("linked_at") if svc.linked_phone(g.member, g.user) else None,
        "morning_plan": bool(p.get("morning_plan")), "new_leads": bool(p.get("new_leads")), "plan_hour": svc.PLAN_HOUR,
        "timezone": g.workspace.timezone or "Asia/Kolkata", "alert_template": bool(i and (i.config or {}).get("team_template")),
        "link": {"code": code, "expires_at": p.get("code_expires_at"), "message": f"LINK {code}",
                 "wa_url": f"https://wa.me/{number}?text={quote(f'LINK {code}')}" if number else None} if code else None,
    }


@bp.get("/me")
@protect()
def me():
    return ok(_view())


@bp.post("/me/link")
@protect()
def link():
    if not _view()["available"]:
        raise ApiError(409, "whatsapp_crm_unavailable", _view()["reason"])
    svc.start_link(g.member, g.user)
    db.session.commit()
    return ok(_view())


class PrefsIn(Schema):
    morning_plan: bool | None = None
    new_leads: bool | None = None


@bp.patch("/me")
@protect()
def update():
    d = parse(PrefsIn)
    svc.save_prefs(g.member, **{k: v for k, v in d.model_dump().items() if v is not None})
    db.session.commit()
    return ok(_view())


@bp.delete("/me")
@protect()
def unlink():
    svc.unlink(g.member)
    db.session.commit()
    return ok(_view())


# ---- admin: the template used for plans and alerts outside the 24-hour window -------------------------------------------

@bp.get("/team-settings")
@protect("integrations.manage")
def team_settings():
    i = wa.connection(g.workspace.id)
    return ok({"team_template": (i.config or {}).get("team_template")})


class TeamIn(Schema):
    team_template: str | None = Field(default=None, max_length=120)  # "name|language", or null to clear


@bp.patch("/team-settings")
@protect("integrations.manage")
def update_team_settings():
    i = wa.connection(g.workspace.id)
    d = parse(TeamIn)
    cfg = dict(i.config or {})
    if d.team_template:
        name, _, lang = d.team_template.partition("|")
        t = next((t for t in wa.list_templates(i) if t["name"] == name and (not lang or t["language"] == lang)), None)
        if t is None or not t["supported"] or t["header"] in ("DOCUMENT", "IMAGE") or t["body_params"] != 1:
            raise ApiError(422, "validation_error", "Pick an approved template with exactly one placeholder and no document or image header.",
                           {"team_template": "Not a usable alert template"})
        cfg["team_template"] = {k: t[k] for k in ("name", "language", "body", "body_params", "param_names")}
    else:
        cfg.pop("team_template", None)
    i.config = cfg
    db.session.commit()
    return ok({"team_template": cfg.get("team_template")})
