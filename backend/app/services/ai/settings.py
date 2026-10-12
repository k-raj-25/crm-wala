"""Bring-your-own-key: each workspace connects its own AI provider.

The key lives Fernet-encrypted in an `integrations` row (provider="ai", workspace-wide) and never leaves the server.
Resolution order for a request: the workspace's own key -> the platform key from env (if the operator set one) -> the
built-in rule-based "basic" mode, so the product keeps working without any key.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from flask import current_app, g, has_request_context
from sqlalchemy import func

from app.extensions import db
from app.models import AiUsage, Integration
from app.services import integrations

PROVIDERS: dict[str, dict] = {
    "openai": {"label": "OpenAI (ChatGPT)", "base_url": "https://api.openai.com/v1", "fast": "gpt-4.1-mini", "smart": "gpt-4.1", "audio": True,
               "key_hint": "Starts with sk-…", "key_url": "https://platform.openai.com/api-keys"},
    "anthropic": {"label": "Anthropic (Claude)", "fast": "claude-haiku-5-5", "smart": "claude-sonnet-5-5", "audio": False,
                  "key_hint": "Starts with sk-ant-…", "key_url": "https://console.anthropic.com/settings/keys"},
    "gemini": {"label": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "fast": "gemini-2.5-flash", "smart": "gemini-2.5-pro",
               "audio": False, "key_hint": "From Google AI Studio", "key_url": "https://aistudio.google.com/app/apikey"},
    "openrouter": {"label": "OpenRouter (any model)", "base_url": "https://openrouter.ai/api/v1", "fast": "openai/gpt-4.1-mini", "smart": "anthropic/claude-sonnet-5-5",
                   "audio": False, "key_hint": "Starts with sk-or-…", "key_url": "https://openrouter.ai/keys"},
}

# Every switch defaults on; admins can turn any of them off for the whole workspace.
FEATURES: list[tuple[str, str, str]] = [
    ("chat", "Ask the assistant", "Questions about leads, flats, visits and reports, with charts."),
    ("actions", "Do it for me", "The assistant prepares changes; nothing is saved until someone presses Approve."),
    ("capture", "Paste, photo or voice to lead", "Turn a WhatsApp forward, visiting card or voice note into a lead."),
    ("visit_log", "Voice log after visits", "Speak after a site visit or call; the assistant logs it and sets the follow-up."),
    ("matching", "Smart flat matching", "Re-ranks flats using preferences in notes and explains each pick."),
    ("whatsapp", "WhatsApp helper", "Suggested replies, chat summaries and requirement capture."),
    ("briefing", "My day", "A morning plan for each person, and a team view for managers."),
    ("search", "Search in plain words", "Type what you want to see; it becomes filters you can save."),
    ("automations", "AI in automations", "Describe an automation in words, plus AI steps inside automations."),
    ("portal", "Portal lead clean-up", "Reads 99acres enquiries, fills the requirement and flags brokers and spam."),
    ("import", "Smart import", "Maps messy spreadsheet columns and cleans phone numbers and budgets."),
    ("insights", "Insights", "Why deals are lost, which flats to push, and weekly coaching."),
    ("writer", "Listing writer", "Project and flat descriptions, WhatsApp broadcasts and portal listings."),
]
FEATURE_KEYS = {k for k, _, _ in FEATURES}


@dataclass
class AIConfig:
    provider: str  # openai | anthropic | gemini | openrouter | mock
    key: str = ""
    fast_model: str = ""
    smart_model: str = ""
    source: str = "basic"  # workspace | platform | basic
    features: dict[str, bool] = field(default_factory=dict)
    mask_pii: bool = False
    monthly_limit: int | None = None
    user_limit: int | None = None
    instructions: str = ""

    def model(self, tier: str) -> str:
        return self.fast_model if tier == "fast" else self.smart_model

    def enabled(self, feature: str) -> bool:
        return self.features.get(feature, True)


def _row(workspace_id) -> Integration | None:
    return integrations.get(workspace_id, "ai")


def resolve(workspace_id=None) -> AIConfig:
    """The provider config for this workspace. Cached per request."""
    wid = workspace_id or (g.workspace.id if has_request_context() and getattr(g, "workspace", None) else None)
    cache = getattr(g, "_ai_cfg", None) if has_request_context() else None
    if cache is not None and cache[0] == wid:
        return cache[1]
    cfg = _resolve(wid)
    if has_request_context():
        g._ai_cfg = (wid, cfg)
    return cfg


def _resolve(wid) -> AIConfig:
    row = _row(wid) if wid else None
    conf = (row.config or {}) if row else {}
    common = dict(features={k: bool(v) for k, v in (conf.get("features") or {}).items() if k in FEATURE_KEYS}, mask_pii=bool(conf.get("mask_pii")),
                  monthly_limit=conf.get("monthly_limit"), user_limit=conf.get("user_limit"), instructions=(conf.get("instructions") or "")[:1000])
    if row and row.status == "connected" and row.credentials_enc:
        p = conf.get("provider")
        key = integrations.get_creds(row).get("api_key", "")
        if p in PROVIDERS and key:
            spec = PROVIDERS[p]
            return AIConfig(p, key, conf.get("fast_model") or spec["fast"], conf.get("smart_model") or spec["smart"], "workspace", **common)
    c = current_app.config
    env = c.get("AI_PROVIDER", "mock")
    env_key = {"anthropic": c.get("ANTHROPIC_API_KEY"), "openai": c.get("OPENAI_API_KEY")}.get(env)
    if env_key:
        spec = PROVIDERS[env]
        model = c.get("AI_MODEL") or spec["smart"]
        return AIConfig(env, env_key, spec["fast"] if not c.get("AI_MODEL") else model, model, "platform", **common)
    return AIConfig("mock", source="basic", **common)


def public_view(workspace_id) -> dict:
    row = _row(workspace_id)
    conf = (row.config or {}) if row else {}
    cfg = resolve(workspace_id)
    last4 = None
    if row and row.credentials_enc:
        k = integrations.get_creds(row).get("api_key", "")
        last4 = k[-4:] if k else None
    return {
        "connected": cfg.source == "workspace", "source": cfg.source, "provider": conf.get("provider") if row else None, "key_last4": last4,
        "fast_model": conf.get("fast_model") or "", "smart_model": conf.get("smart_model") or "", "status": row.status if row else "not_connected",
        "last_error": row.last_error if row else None, "connected_at": row.updated_at.isoformat() if row and row.status == "connected" else None,
        "features": {k: cfg.enabled(k) for k in FEATURE_KEYS}, "mask_pii": cfg.mask_pii, "monthly_limit": cfg.monthly_limit, "user_limit": cfg.user_limit,
        "instructions": cfg.instructions, "active_provider": cfg.provider, "active_model": cfg.smart_model or None,
        "providers": [{"key": k, **{f: v for f, v in s.items() if f != "base_url"}} for k, s in PROVIDERS.items()],
        "feature_list": [{"key": k, "label": l, "description": d} for k, l, d in FEATURES],
        "usage": usage_summary(workspace_id),
    }


def save(workspace_id, *, provider: str | None = None, api_key: str | None = None, fast_model: str | None = None, smart_model: str | None = None,
         features: dict | None = None, mask_pii: bool | None = None, monthly_limit: int | None | str = "keep", user_limit: int | None | str = "keep",
         instructions: str | None = None) -> Integration:
    row = integrations.upsert(workspace_id, "ai")
    conf = dict(row.config or {})
    if provider is not None:
        if conf.get("provider") != provider:  # a key belongs to one provider; switching needs a new key
            row.credentials_enc = None
            row.status = "not_connected"
            conf.pop("fast_model", None)
            conf.pop("smart_model", None)
        conf["provider"] = provider
    if api_key:
        integrations.set_creds(row, {"api_key": api_key.strip()})
        row.status, row.last_error = "connected", None
        row.connected_by = g.user.id if has_request_context() and getattr(g, "user", None) else None
    if fast_model is not None:
        conf["fast_model"] = fast_model.strip()[:80]
    if smart_model is not None:
        conf["smart_model"] = smart_model.strip()[:80]
    if features is not None:
        conf["features"] = {**(conf.get("features") or {}), **{k: bool(v) for k, v in features.items() if k in FEATURE_KEYS}}
    if mask_pii is not None:
        conf["mask_pii"] = bool(mask_pii)
    if monthly_limit != "keep":
        conf["monthly_limit"] = monthly_limit
    if user_limit != "keep":
        conf["user_limit"] = user_limit
    if instructions is not None:
        conf["instructions"] = instructions.strip()[:1000]
    row.config = conf
    row.account_label = PROVIDERS.get(conf.get("provider") or "", {}).get("label")
    if has_request_context():
        g.pop("_ai_cfg", None)
    return row


def disconnect(workspace_id) -> None:
    row = _row(workspace_id)
    if row:
        row.credentials_enc, row.status, row.last_error = None, "not_connected", None
    if has_request_context():
        g.pop("_ai_cfg", None)


def mark_error(workspace_id, message: str) -> None:
    row = _row(workspace_id)
    if row and row.status == "connected":
        row.last_error = message[:400]


def month_start() -> dt.datetime:
    now = dt.datetime.now(dt.timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage_summary(workspace_id, user_id=None) -> dict:
    q = db.session.query(func.count(AiUsage.id), func.coalesce(func.sum(AiUsage.input_tokens), 0), func.coalesce(func.sum(AiUsage.output_tokens), 0)).filter(
        AiUsage.workspace_id == workspace_id, AiUsage.created_at >= month_start())
    if user_id:
        q = q.filter(AiUsage.user_id == user_id)
    n, tin, tout = q.one()
    by_feature = dict(db.session.query(AiUsage.feature, func.count()).filter(AiUsage.workspace_id == workspace_id, AiUsage.created_at >= month_start()).group_by(AiUsage.feature).all())
    return {"actions": n, "input_tokens": int(tin), "output_tokens": int(tout), "by_feature": by_feature}
