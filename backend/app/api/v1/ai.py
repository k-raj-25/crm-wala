from __future__ import annotations

import re
import uuid

from flask import Blueprint, g, request
from pydantic import Field

from app.core.auth import protect
from app.core.errors import ApiError, bad_request, not_found
from app.core.responses import no_content, ok
from app.extensions import db, limiter
from app.models import AiConversation, Lead, Meeting
from app.models.base import utcnow
from app.schemas.common import Schema, parse
from app.services import analytics, audit, privacy
from app.services.ai import assistant, features, insights, settings as ai_settings, tools
from app.services.features import plan_limits
from app.services.usage import current_usage

bp = Blueprint("ai", __name__, url_prefix="/api/v1/ai")
bp.after_request(privacy.mask_response)
CHAT, INSIGHTS = dict(perm="ai.use", feature="ai_assistant"), dict(perm="ai.use", feature="ai_insights")


def _usage() -> dict:
    lim = plan_limits(g.workspace).get("ai_actions_month")
    used = current_usage(g.workspace)["ai_actions_month"]
    return {"used": used, "limit": lim}


@bp.get("/usage")
@protect("ai.use", feature="ai_assistant")
def usage():
    return ok(_usage())


class PageIn(Schema):
    entity: str | None = Field(default=None, pattern="^(lead|contact|deal|company|project|unit)$")
    id: str | None = Field(default=None, max_length=64)
    label: str | None = Field(default=None, max_length=160)
    path: str | None = Field(default=None, max_length=300)


class ChatIn(Schema):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    page: PageIn | None = None


@bp.post("/chat")
@protect(**CHAT)
@limiter.limit("30 per minute")
def chat():
    d = parse(ChatIn)
    conv = None
    if d.conversation_id:
        conv = db.session.query(AiConversation).filter_by(id=d.conversation_id, workspace_id=g.workspace.id, user_id=g.user.id).one_or_none()
        if conv is None:
            raise not_found("Conversation")
    if conv is None:
        conv = AiConversation(workspace_id=g.workspace.id, user_id=g.user.id, title=d.message[:60], messages=[])
        db.session.add(conv)
    assistant.require_feature("chat")
    history = [{"role": m["role"], "content": m["content"]} for m in conv.messages] + [{"role": "user", "content": d.message}]
    page = d.page.model_dump() if d.page else None
    g.ai_page = page
    res, proposals = assistant.ask(history, page)
    now = utcnow().isoformat()
    # Proposals are kept with the message; /proposals/outcome stamps their status so a reopened conversation shows what already ran.
    conv.messages = [*conv.messages, {"role": "user", "content": d.message, "at": now},
                     {"role": "assistant", "content": res.text, "sources": res.sources, "charts": res.charts, "proposals": proposals, "at": now}][-60:]
    analytics.track("ai_chat")
    db.session.commit()
    return ok({"conversation_id": str(conv.id), "answer": res.text, "sources": res.sources, "charts": res.charts, "proposals": proposals, "usage": _usage()})


@bp.get("/conversations")
@protect(**CHAT)
def conversations():
    rows = db.session.query(AiConversation).filter_by(workspace_id=g.workspace.id, user_id=g.user.id).order_by(AiConversation.updated_at.desc()).limit(30).all()
    return ok([{"id": str(c.id), "title": c.title, "updated_at": c.updated_at.isoformat()} for c in rows])


@bp.get("/conversations/<uuid:cid>")
@protect(**CHAT)
def conversation(cid):
    c = db.session.query(AiConversation).filter_by(id=cid, workspace_id=g.workspace.id, user_id=g.user.id).one_or_none()
    if c is None:
        raise not_found("Conversation")
    return ok({"id": str(c.id), "title": c.title, "messages": c.messages})


@bp.delete("/conversations/<uuid:cid>")
@protect(**CHAT)
def delete_conversation(cid):
    db.session.query(AiConversation).filter_by(id=cid, workspace_id=g.workspace.id, user_id=g.user.id).delete()
    db.session.commit()
    return no_content()


class DraftIn(Schema):
    entity: str = Field(pattern="^(lead|contact|deal|company)$")
    id: uuid.UUID
    goal: str = Field(default="follow_up", pattern="^(follow_up|intro|proposal|meeting|check_in|win_back)$")
    instructions: str | None = Field(default=None, max_length=500)


@bp.post("/email-draft")
@protect(**CHAT)
@limiter.limit("30 per minute")
def email_draft():
    d = parse(DraftIn)
    ctx = tools.record_context(d.entity, str(d.id))
    if "error" in ctx:
        raise not_found("Record")
    ctx.update(goal=d.goal, sender=g.user.name)
    prompt = (f"Write a concise, warm, professional sales email from {g.user.name} (goal: {d.goal.replace('_', ' ')}) to the contact below. Return the first line as 'SUBJECT: …', then a blank line, then the body. "
              f"{'Extra instructions: ' + d.instructions if d.instructions else ''}\n\nCRM context:\n{assistant.ctx(ctx)}")
    res = assistant.generate("email_draft", prompt, ctx, "email_draft")
    subject, body = "Following up", res.text
    m = re.match(r"\s*SUBJECT:\s*(.+?)\n+(.*)", res.text, re.S | re.I)
    if m:
        subject, body = m.group(1).strip(), m.group(2).strip()
    db.session.commit()
    return ok({"subject": subject, "body": body, "usage": _usage()})


class SummaryIn(Schema):
    entity: str = Field(pattern="^(lead|contact|deal|company)$")
    id: uuid.UUID


@bp.post("/summarize")
@protect(**CHAT)
@limiter.limit("30 per minute")
def summarize():
    d = parse(SummaryIn)
    ctx = tools.record_context(d.entity, str(d.id))
    if "error" in ctx:
        raise not_found("Record")
    res = assistant.generate("summary", f"Summarize this CRM record for a salesperson in 4-6 short lines, ending with a suggested next step.\n\n{assistant.ctx(ctx)}", ctx, "summary")
    db.session.commit()
    return ok({"summary": res.text, "ai": res.provider != "mock", "usage": _usage()})


class MeetingSummaryIn(Schema):
    meeting_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=20000)


@bp.post("/meeting-summary")
@protect(**CHAT)
def meeting_summary():
    d = parse(MeetingSummaryIn)
    m = db.session.query(Meeting).filter_by(id=d.meeting_id, workspace_id=g.workspace.id, deleted_at=None).one_or_none()
    if m is None:
        raise not_found("Meeting")
    notes = d.notes or m.summary or m.description or ""
    if not notes.strip():
        raise bad_request("Add meeting notes first so there's something to summarize.", "no_notes")
    res = assistant.generate("meeting_summary", f"Summarize these meeting notes and list action items:\n\n{notes}", {"notes": notes}, "meeting_summary")
    db.session.commit()
    return ok({"summary": res.text, "ai": res.provider != "mock", "usage": _usage()})


@bp.get("/next-best-actions")
@protect(**INSIGHTS)
def nba():
    return ok(insights.next_best_actions())


@bp.get("/churn-risk")
@protect(**INSIGHTS)
def churn():
    return ok(insights.churn_risk(int(request.args.get("inactive_days", 45))))


@bp.get("/data-cleanup")
@protect(**INSIGHTS)
def cleanup():
    return ok(insights.data_cleanup())


@bp.get("/pipeline-diagnosis")
@protect(**INSIGHTS)
def diagnosis():
    return ok(insights.pipeline_diagnosis(int(request.args.get("days", 30))))


@bp.post("/rescore-leads")
@protect("leads.update", feature="ai_assistant")
def rescore_leads():
    from app.api.v1.leads import rescore

    n = 0
    for lead in db.session.query(Lead).filter(Lead.workspace_id == g.workspace.id, Lead.deleted_at.is_(None), Lead.status.in_(("new", "contacted", "qualified"))).limit(5000):
        rescore(lead)
        n += 1
    db.session.commit()
    return ok({"rescored": n})


# ---- Bring your own key ---------------------------------------------------------------------------------------------------

@bp.get("/status")
@protect("ai.use", feature="ai_assistant")
def ai_status():
    cfg = ai_settings.resolve()
    spec = ai_settings.PROVIDERS.get(cfg.provider, {})
    return ok({"mode": cfg.source, "provider": cfg.provider, "provider_label": spec.get("label", "Basic (no AI key)"), "model": cfg.smart_model or None,
               "features": {k: cfg.enabled(k) for k in ai_settings.FEATURE_KEYS}, "audio_files": bool(spec.get("audio")), "photos": cfg.provider != "mock",
               "can_manage": tools._can("settings.manage")})


@bp.get("/settings")
@protect("settings.manage", feature="ai_assistant")
def get_settings():
    return ok(ai_settings.public_view(g.workspace.id))


class SettingsIn(Schema):
    provider: str | None = Field(default=None, pattern="^(openai|anthropic|gemini|openrouter)$")
    api_key: str | None = Field(default=None, min_length=8, max_length=400)
    fast_model: str | None = Field(default=None, max_length=80)
    smart_model: str | None = Field(default=None, max_length=80)
    features: dict[str, bool] | None = None
    mask_pii: bool | None = None
    monthly_limit: int | None = Field(default=None, ge=1, le=1_000_000)
    user_limit: int | None = Field(default=None, ge=1, le=1_000_000)
    instructions: str | None = Field(default=None, max_length=1000)


def _ping(provider: str, key: str, model: str | None) -> tuple[str, str | None]:
    """Sends a tiny test message. Returns (model that answered, fallback model to save or None).

    When nobody typed a model and the recommended one has been retired, the provider's fallback is tried, so a stale default
    never blocks a valid key."""
    from app.services.ai.providers import AnthropicProvider, OpenAIProvider

    spec = ai_settings.PROVIDERS[provider]

    def send(m: str):
        p = AnthropicProvider(key, m, 20) if provider == "anthropic" else OpenAIProvider(key, m, spec["base_url"], provider, 20)
        return p.complete("ping", "Reply with the single word OK.", "Say OK", {}, None, 64)

    tried = model or spec["fast"]
    try:
        return send(tried).model or "", None
    except ApiError as e:
        if e.code == "ai_model_missing" and not model and spec.get("fallback"):
            try:
                return send(spec["fallback"]).model or "", spec["fallback"]
            except ApiError as e2:
                e = e2
        if e.code == "ai_model_missing":
            raise ApiError(400, e.code, f"{spec['label']} doesn't offer the model \"{tried}\" on this key. Type a model your account can use under Models, or leave it blank for the recommended one.")
        raise ApiError(400, e.code, e.message)


@bp.put("/settings")
@protect("settings.manage", feature="ai_assistant")
@limiter.limit("20 per minute")
def put_settings():
    d = parse(SettingsIn)
    sent = d.model_fields_set
    row = ai_settings._row(g.workspace.id)
    provider = d.provider or ((row.config or {}).get("provider") if row else None)
    if d.api_key and not provider:
        raise bad_request("Choose which AI provider the key is for.", "provider_required")
    fast_model, smart_model = d.fast_model, d.smart_model
    if d.api_key:
        conf = (row.config or {}) if row and (not d.provider or (row.config or {}).get("provider") == d.provider) else {}
        _, fallback = _ping(provider, d.api_key.strip(), (d.fast_model if "fast_model" in sent else conf.get("fast_model")) or None)
        if fallback:  # the recommended models are retired on this key; save the one that answered
            fast_model = fallback
            smart_model = smart_model or conf.get("smart_model") or fallback
    before = ai_settings.public_view(g.workspace.id)
    ai_settings.save(g.workspace.id, provider=d.provider, api_key=d.api_key, fast_model=fast_model, smart_model=smart_model, features=d.features,
                     mask_pii=d.mask_pii, monthly_limit=d.monthly_limit if "monthly_limit" in sent else "keep", user_limit=d.user_limit if "user_limit" in sent else "keep",
                     instructions=d.instructions)
    db.session.flush()
    after = ai_settings.public_view(g.workspace.id)
    keep = ("provider", "key_last4", "fast_model", "smart_model", "features", "mask_pii", "monthly_limit", "user_limit")
    audit.record("ai.settings_updated", entity_type="workspace", entity_id=g.workspace.id, summary="Updated AI assistant settings" + (" (new key)" if d.api_key else ""),
                 before={k: before[k] for k in keep}, after={k: after[k] for k in keep})
    db.session.commit()
    return ok(after)


@bp.post("/settings/test")
@protect("settings.manage", feature="ai_assistant")
@limiter.limit("10 per minute")
def test_settings():
    cfg = ai_settings.resolve()
    if cfg.source != "workspace":
        raise bad_request("Connect a key first.", "not_connected")
    row = ai_settings._row(g.workspace.id)
    model, fallback = _ping(cfg.provider, cfg.key, (row.config or {}).get("fast_model") or None)
    if fallback:
        ai_settings.save(g.workspace.id, fast_model=fallback, smart_model=(row.config or {}).get("smart_model") or fallback)
    row.last_error = None
    db.session.commit()
    return ok({"ok": True, "model": model})


@bp.delete("/settings/key")
@protect("settings.manage", feature="ai_assistant")
def delete_key():
    ai_settings.disconnect(g.workspace.id)
    audit.record("ai.key_removed", entity_type="workspace", entity_id=g.workspace.id, summary="Removed the AI provider key")
    db.session.commit()
    return ok(ai_settings.public_view(g.workspace.id))


# ---- Feature endpoints ----------------------------------------------------------------------------------------------------

class ImageIn(Schema):
    media_type: str = Field(pattern="^image/(png|jpeg|webp|gif)$")
    data: str = Field(min_length=10, max_length=7_000_000)  # base64, ~5 MB


class CaptureIn(Schema):
    text: str | None = Field(default=None, max_length=20000)
    images: list[ImageIn] = Field(default_factory=list, max_length=3)
    source: str | None = Field(default=None, max_length=60)


@bp.post("/capture")
@protect("leads.create", feature="ai_assistant")
@limiter.limit("30 per minute")
def capture():
    d = parse(CaptureIn)
    return ok(features.capture(d.text, [i.model_dump() for i in d.images], d.source))


@bp.post("/transcribe")
@protect("ai.use", feature="ai_assistant")
@limiter.limit("20 per minute")
def transcribe():
    f = request.files.get("file")
    if f is None:
        raise bad_request("Attach an audio file.", "no_file")
    data = f.read()
    if len(data) > 24 * 1024 * 1024:
        raise ApiError(413, "payload_too_large", "Audio files up to 24 MB are supported.")
    return ok({"text": features.transcribe(data, f.filename or "voice.webm", f.mimetype or "audio/webm")})


class VisitLogIn(Schema):
    lead_id: uuid.UUID
    text: str = Field(min_length=3, max_length=8000)
    kind: str = Field(default="visit", pattern="^(visit|call)$")
    when: str | None = Field(default=None, max_length=40)


@bp.post("/visit-log")
@protect("ai.use", feature="ai_assistant")
@limiter.limit("30 per minute")
def visit_log():
    d = parse(VisitLogIn)
    return ok(features.visit_log(d.lead_id, d.text, d.kind, d.when))


@bp.get("/leads/<uuid:lead_id>/smart-matches")
@protect("units.read", feature="ai_assistant")
def smart_matches(lead_id):
    return ok(features.smart_matches(lead_id))


@bp.get("/units/<uuid:unit_id>/lead-matches")
@protect("leads.read", feature="ai_assistant")
def unit_lead_matches(unit_id):
    return ok(features.unit_leads(unit_id))


class WhatsAppIn(Schema):
    conversation: str = Field(default="", max_length=30000)
    lead_id: uuid.UUID | None = None
    goal: str | None = Field(default=None, max_length=300)


@bp.post("/whatsapp-assist")
@protect("ai.use", feature="ai_assistant")
@limiter.limit("30 per minute")
def whatsapp_assist():
    d = parse(WhatsAppIn)
    return ok(features.whatsapp_assist(d.conversation, d.lead_id, d.goal))


@bp.get("/my-day")
@protect("ai.use", feature="ai_assistant")
def my_day():
    return ok(features.my_day(team=request.args.get("team") == "1" and tools._can("reports.read")))


@bp.post("/my-day/intro")
@protect("ai.use", feature="ai_assistant")
@limiter.limit("10 per minute")
def my_day_intro():
    body = request.get_json(silent=True) or {}
    return ok({"text": features.my_day_intro(team=bool(body.get("team")) and tools._can("reports.read"))})


class SearchIn(Schema):
    query: str = Field(min_length=2, max_length=300)
    entity: str = "leads"


@bp.post("/parse-search")
@protect("leads.read", feature="ai_assistant")
@limiter.limit("40 per minute")
def parse_search():
    d = parse(SearchIn)
    return ok(features.parse_search(d.query, d.entity))


class AutomationDraftIn(Schema):
    text: str = Field(min_length=8, max_length=1000)


@bp.post("/automation-draft")
@protect("automations.create", feature="automation_builder")
@limiter.limit("20 per minute")
def automation_draft():
    return ok(features.automation_draft(parse(AutomationDraftIn).text))


class ImportAssistIn(Schema):
    entity: str = Field(pattern="^(leads|contacts|companies|deals)$")
    headers: list[str] = Field(max_length=200)
    rows: list[dict] = Field(default_factory=list, max_length=20)


@bp.post("/import-assist")
@protect("data.import", feature="ai_assistant")
@limiter.limit("20 per minute")
def import_assist():
    d = parse(ImportAssistIn)
    return ok(features.import_assist(d.entity, d.headers, d.rows))


@bp.get("/data-fixes")
@protect("leads.update", feature="ai_assistant")
def data_fixes():
    return ok(features.data_fixes())


@bp.get("/loss-analysis")
@protect("reports.read", feature="ai_insights")
def loss_analysis():
    return ok(features.loss_analysis(max(7, min(int(request.args.get("days", 180)), 730))))


@bp.get("/inventory-advice")
@protect("units.read", feature="ai_insights")
def inventory_advice():
    return ok(features.inventory_advice())


@bp.get("/coaching")
@protect("reports.read", feature="ai_insights")
def coaching():
    return ok(features.coaching(max(1, min(int(request.args.get("days", 7)), 90))))


class ListingIn(Schema):
    kind: str = Field(pattern="^(description|whatsapp|portal)$")
    project_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    language: str = Field(default="english", max_length=30)
    notes: str | None = Field(default=None, max_length=500)


@bp.post("/listing")
@protect("projects.read", feature="ai_assistant")
@limiter.limit("30 per minute")
def listing():
    d = parse(ListingIn)
    return ok(features.listing(d.kind, d.project_id, d.unit_id, d.language, d.notes))


class OutcomeIn(Schema):
    kind: str = Field(max_length=40)
    title: str = Field(max_length=300)
    outcome: str = Field(pattern="^(approved|cancelled|undone|failed)$")
    calls: int = Field(default=0, ge=0, le=1000)
    error: str | None = Field(default=None, max_length=300)
    proposal_id: str | None = Field(default=None, max_length=40)
    result_url: str | None = Field(default=None, max_length=300)


def _remember_outcome(pid: str, outcome: str, result_url: str | None) -> None:
    """Stamp the card in the saved conversation, so reopening the chat shows it as done instead of asking again."""
    rows = db.session.query(AiConversation).filter_by(workspace_id=g.workspace.id, user_id=g.user.id).order_by(AiConversation.updated_at.desc()).limit(30).all()
    for conv in rows:
        msgs = [dict(m) for m in conv.messages or []]
        for m in msgs:
            props = m.get("proposals") or []
            if any(p.get("id") == pid for p in props):
                m["proposals"] = [{**p, "status": outcome, **({"result_url": result_url} if result_url else {})} if p.get("id") == pid else p for p in props]
                conv.messages = msgs  # reassign so the JSON column is saved
                return


@bp.post("/proposals/outcome")
@protect("ai.use", feature="ai_assistant")
def proposal_outcome():
    """The browser reports what happened to a card, so admins can see AI-made changes in the audit log."""
    d = parse(OutcomeIn)
    analytics.track(f"ai_proposal_{d.outcome}")
    if d.outcome in ("approved", "undone", "failed"):
        audit.record(f"ai.proposal_{d.outcome}", summary=f"{d.title} — {d.outcome} via AI assistant" + (f" ({d.error})" if d.error else ""),
                     after={"kind": d.kind, "calls": d.calls})
    if d.proposal_id and d.outcome != "failed":
        _remember_outcome(d.proposal_id, d.outcome, d.result_url if d.result_url and d.result_url.startswith("/app/") else None)
    db.session.commit()
    return no_content()
