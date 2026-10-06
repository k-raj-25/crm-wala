from __future__ import annotations

from flask import g

from app.core.errors import ApiError
from app.extensions import db
from app.models import AiUsage
from app.services.ai import tools
from app.services.ai.providers import AIResult, get_provider
from app.services.usage import check_limit

SYSTEM = (
    "You are the AI assistant inside a CRM for the user's company. Answer ONLY using data returned by your tools; never invent records, "
    "numbers or names. If a tool returns an error or no data, say so plainly. Be concise and actionable: lead with the answer, then short bullets. "
    "Use markdown links to records using the `url` fields provided. Currency amounts are in the record's currency. "
    "You only have access to the current user's workspace and permissions."
)


def meter(feature: str) -> None:
    check_limit(g.workspace, "ai_actions_month")


def record_usage(feature: str, res: AIResult, provider_name: str) -> None:
    db.session.add(AiUsage(workspace_id=g.workspace.id, user_id=g.user.id, feature=feature, provider=provider_name, model=res.model, input_tokens=res.input_tokens, output_tokens=res.output_tokens))


def generate(kind: str, prompt: str, context: dict, feature: str) -> AIResult:
    meter(feature)
    p = get_provider()
    res = p.complete(kind, SYSTEM, prompt, context)
    record_usage(feature, res, p.name)
    return res


def ask(history: list[dict]) -> AIResult:
    meter("chat")
    p = get_provider()
    res = p.chat(SYSTEM, history[-12:], tools.TOOL_SPECS, tools.run_tool)
    record_usage("chat", res, p.name)
    return res
