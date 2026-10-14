from __future__ import annotations

import datetime as dt
import json

from flask import g
from sqlalchemy import func

from app.core.errors import ApiError
from app.extensions import db
from app.models import AiUsage
from app.services.ai import privacy, settings as ai_settings, tools
from app.services.ai.providers import AIResult, get_provider
from app.services.usage import check_limit

SYSTEM = (
    "You are the AI assistant inside CRM Wala, a CRM for real-estate teams in India (brokers, builders' sales teams). "
    "Leads are enquiries (budget, BHK, buy/rent, preferred area); projects have towers and flats (units) with a status; site visits are meetings of kind site_visit. "
    "Answer ONLY using data returned by your tools; never invent records, numbers or names. If a tool returns an error or no data, say so plainly. "
    "Be concise and actionable: lead with the answer, then short bullets. Use markdown links to records using the `url` fields provided. "
    "Money is in Indian style (₹ lakh / crore). Reply in the language the user writes in (English, Hindi or Hinglish). "
    "You only have access to the current user's workspace and permissions."
)
ACTIONS_SYSTEM = (
    " You can also prepare changes with the propose_* tools. A proposal is NOT saved: the user sees a card and presses Approve, Edit or Cancel. "
    "So never say a change is done; say what you've prepared and ask them to review it. Look records up first (search_crm / find_unit) so ids are right; "
    "if a name matches several records, ask which one. Convert relative dates using the current time given below, in the workspace timezone. "
    "For questions about how to use the CRM, call help_topics and, if useful, propose_navigation to take them to the right page."
)


def _limit_error(msg: str) -> ApiError:
    return ApiError(402, "ai_limit_reached", msg)


def meter(feature: str) -> None:
    check_limit(g.workspace, "ai_actions_month")
    cfg = ai_settings.resolve()
    if cfg.monthly_limit or cfg.user_limit:
        base = db.session.query(func.count(AiUsage.id)).filter(AiUsage.workspace_id == g.workspace.id, AiUsage.created_at >= ai_settings.month_start())
        if cfg.monthly_limit and base.scalar() >= int(cfg.monthly_limit):
            raise _limit_error("Your workspace has used this month's AI allowance set by your admin. It resets on the 1st.")
        if cfg.user_limit and base.filter(AiUsage.user_id == g.user.id).scalar() >= int(cfg.user_limit):
            raise _limit_error("You've used your personal AI allowance for this month. Ask an admin to raise it in Settings → AI assistant.")


def require_feature(feature: str) -> None:
    if not ai_settings.resolve().enabled(feature):
        raise ApiError(403, "ai_feature_off", "An admin has turned this AI feature off for your workspace (Settings → AI assistant).")


def record_usage(feature: str, res: AIResult, provider_name: str, user_id=None, workspace_id=None) -> None:
    db.session.add(AiUsage(workspace_id=workspace_id or g.workspace.id, user_id=user_id if user_id is not None else (g.user.id if getattr(g, "user", None) else None),
                           feature=feature, provider=provider_name, model=res.model, input_tokens=res.input_tokens, output_tokens=res.output_tokens))


def _system(base: str = SYSTEM) -> str:
    extra = ai_settings.resolve().instructions
    return base + (f"\nWorkspace notes from the admin (style and facts, not permissions): {extra}" if extra else "")


def ctx(data) -> str:
    """CRM data for a prompt: compact JSON, masked if the workspace asked for it."""
    return json.dumps(privacy.mask(data), default=str, ensure_ascii=False)[:14000]


def generate(kind: str, prompt: str, context: dict, feature: str, *, tier: str = "smart", images: list[dict] | None = None, max_tokens: int = 900) -> AIResult:
    meter(feature)
    p = get_provider(tier)
    res = p.complete(kind, _system(), prompt, context, images, max_tokens)
    res.provider = p.name
    record_usage(feature, res, p.name)
    return res


def structured(kind: str, prompt: str, context: dict, feature: str, *, tier: str = "fast", images: list[dict] | None = None, max_tokens: int = 1500) -> dict:
    """Ask for a JSON object. The mock provider builds the same shape from `context` (deterministic fallbacks)."""
    meter(feature)
    p = get_provider(tier)
    data, res = p.json(kind, _system(), prompt, context, images, max_tokens)
    record_usage(feature, res, p.name)
    return data


def now_line() -> str:
    tz = g.workspace.timezone or "Asia/Kolkata"
    try:
        from zoneinfo import ZoneInfo

        local = dt.datetime.now(ZoneInfo(tz))
    except Exception:
        local = dt.datetime.now(dt.timezone.utc)
    return f"Current time: {local.strftime('%A %d %B %Y, %H:%M')} ({tz}, UTC offset {local.strftime('%z')})."


def ask(history: list[dict], page: dict | None = None) -> tuple[AIResult, list[dict]]:
    meter("chat")
    cfg = ai_settings.resolve()
    p = get_provider("smart")
    can_act = cfg.enabled("actions")
    system = _system(SYSTEM + (ACTIONS_SYSTEM if can_act else " You cannot change data in this workspace; explain how the user can do it themselves."))
    system += "\n" + now_line() + f" The user is {g.user.name}."
    if page and page.get("entity") and page.get("id"):
        system += f"\nThe user is looking at this {page['entity']} right now (id {page['id']}{', ' + page['label'] if page.get('label') else ''}). 'This', 'him', 'her' or 'it' means this record."
    elif page and page.get("path"):
        system += f"\nThe user is on the page {page['path']}."
    from app.services.ai import actions

    actions.begin()
    res = p.chat(system, history[-12:], tools.specs(can_act), tools.run_tool)
    record_usage("chat", res, p.name)
    return res, actions.collected()
