from __future__ import annotations

import re
import uuid

from flask import Blueprint, g, request
from pydantic import Field
from sqlalchemy import func

from app.core.auth import protect
from app.core.errors import ApiError, bad_request, not_found
from app.core.responses import no_content, ok
from app.extensions import db, limiter
from app.models import AiConversation, AiUsage, Deal, Lead, Meeting
from app.models.base import utcnow
from app.schemas.common import Schema, parse
from app.services import analytics, scoring
from app.services.ai import assistant, insights, tools
from app.services.features import plan_limits
from app.services.usage import current_usage

bp = Blueprint("ai", __name__, url_prefix="/api/v1/ai")
CHAT, INSIGHTS = dict(perm="ai.use", feature="ai_assistant"), dict(perm="ai.use", feature="ai_insights")


def _usage() -> dict:
    lim = plan_limits(g.workspace).get("ai_actions_month")
    used = current_usage(g.workspace)["ai_actions_month"]
    return {"used": used, "limit": lim}


@bp.get("/usage")
@protect("ai.use", feature="ai_assistant")
def usage():
    return ok(_usage())


class ChatIn(Schema):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None


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
    history = [{"role": m["role"], "content": m["content"]} for m in conv.messages] + [{"role": "user", "content": d.message}]
    res = assistant.ask(history)
    now = utcnow().isoformat()
    conv.messages = [*conv.messages, {"role": "user", "content": d.message, "at": now}, {"role": "assistant", "content": res.text, "sources": res.sources, "at": now}][-60:]
    analytics.track("ai_chat")
    db.session.commit()
    return ok({"conversation_id": str(conv.id), "answer": res.text, "sources": res.sources, "usage": _usage()})


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
              f"{'Extra instructions: ' + d.instructions if d.instructions else ''}\n\nCRM context:\n{ctx}")
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
    res = assistant.generate("summary", f"Summarize this CRM record for a salesperson in 4-6 short lines, ending with a suggested next step.\n\n{ctx}", ctx, "summary")
    db.session.commit()
    return ok({"summary": res.text, "usage": _usage()})


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
    return ok({"summary": res.text, "usage": _usage()})


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
