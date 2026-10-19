"""The CRM inside WhatsApp: reps update the CRM by messaging the company's own WhatsApp Business number.

A rep links their number once (Notifications settings → WhatsApp): the CRM shows a one-time code and the rep sends it from
the phone number on their profile, which proves the number is theirs. From then on, messages from that number are the
rep's, never a client's, and never become leads:

- a text or voice note ("Visited Priya, liked 1502, follow up Sunday") becomes the same proposals the AI assistant makes
  in the app, sent back as a card with Confirm / Cancel buttons. Nothing is saved until the rep taps Confirm; the calls
  then run as the rep through the normal API, so permissions, validation, audit and automations all apply;
- "plan" sends today's plan; opted-in reps also get it every morning, plus an alert for each new lead they're given.

Voice notes are turned into text with the workspace's AI key; without a key that can transcribe audio, the rep is asked
to send text. Outside WhatsApp's 24-hour window the CRM can only start a conversation with an approved template, so the
morning plan and alerts use the "team alert template" an admin picks (one placeholder); a reply opens the window again.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import secrets
from contextlib import contextmanager
from typing import Any

import httpx
from flask import current_app, g, has_request_context, request
from sqlalchemy import func

from app.core.errors import ApiError
from app.core.permissions import has_permission
from app.core.tenant import tenant_scope
from app.extensions import db
from app.models import Integration, Lead, Notification, User, WhatsAppMessage, Workspace, WorkspaceMember
from app.models.base import utcnow
from app.services import integrations, privacy, whatsapp as wa

log = logging.getLogger("app.whatsapp_crm")

PREFS_KEY = "whatsapp"
PLAN_HOUR = 9  # local time in the workspace's timezone (India by default)
CODE_TTL = dt.timedelta(minutes=30)
CARD_TTL = dt.timedelta(hours=24)
UNDO_TTL = dt.timedelta(minutes=15)
MAX_CARDS = 3
LINK_RE = re.compile(r"^\s*link\s+(\d{6})\s*$", re.I)
VISIT_WORDS = re.compile(r"\b(visit(ed)?|site|showed|saw|dekh[aie]|met|meeting)\b", re.I)
NEW_LEAD = re.compile(r"^\s*new\s+(lead|enquiry|inquiry|client)\s*[:,-]?\s*", re.I)
CALL_WORDS = re.compile(r"\b(call(ed)?|spoke|phone|rang|baat)\b", re.I)
HELP = (
    "*CRM Wala on WhatsApp*\n"
    "Send me an update as text or a voice note, for example:\n"
    "• Visited Priya, liked 1502, follow up Sunday\n"
    "• Called Rahul, budget now 1.2 Cr, call back tomorrow\n"
    "• New lead Neha 98765 43210, 3 BHK in Baner, 1.5 Cr\n"
    "I'll send a card to confirm before anything is saved.\n\n"
    "Other things you can send: *plan* (today's plan), *plan on* / *plan off* (morning plan at 9 AM), "
    "*alerts on* / *alerts off* (new lead alerts), *cancel* (drop cards waiting for you)."
)


# ---- rep settings (kept on the membership, so they're per workspace) -----------------------------------------------

def prefs(member: WorkspaceMember) -> dict:
    return dict((member.notification_prefs or {}).get(PREFS_KEY) or {})


def save_prefs(member: WorkspaceMember, **changes) -> dict:
    p = {k: v for k, v in {**prefs(member), **changes}.items() if v is not None}
    member.notification_prefs = {**(member.notification_prefs or {}), PREFS_KEY: p}
    return p


def company_number(i: Integration | None) -> str | None:
    """The business number as Meta shows it, from the label saved when WhatsApp was connected ("Acme Realty · +91 99999 00000")."""
    if not i or not i.account_label or " · " not in i.account_label:
        return None
    n = wa.normalize_phone(i.account_label.rsplit(" · ", 1)[1])
    return n


def linked_phone(member: WorkspaceMember, user: User) -> str | None:
    """The rep's linked number, as long as it is still the phone on their profile."""
    p = prefs(member).get("phone")
    return p if p and wa.normalize_phone(user.phone) == p else None


def start_link(member: WorkspaceMember, user: User) -> dict:
    phone = wa.normalize_phone(user.phone)
    if not phone:
        raise ApiError(422, "validation_error", "Add your mobile number to your profile first. Messages from that number will be yours.",
                       {"phone": "Add a mobile number"})
    clash = _rep_rows(member.workspace_id, phone)
    if any(m.id != member.id for m, _ in clash):
        raise ApiError(409, "phone_in_use", "Another teammate has already linked this number.")
    code = f"{secrets.randbelow(10 ** 6):06d}"
    save_prefs(member, code=code, code_expires_at=(utcnow() + CODE_TTL).isoformat())
    return {"code": code, "phone": phone}


def unlink(member: WorkspaceMember) -> None:
    p = prefs(member)
    member.notification_prefs = {**(member.notification_prefs or {}), PREFS_KEY: {k: v for k, v in p.items() if k in ("morning_plan", "new_leads")}}


def _rep_rows(workspace_id, phone: str) -> list[tuple[WorkspaceMember, User]]:
    return db.session.query(WorkspaceMember, User).join(User, User.id == WorkspaceMember.user_id).filter(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.status == "active",
        WorkspaceMember.notification_prefs[PREFS_KEY]["phone"].astext == phone).all()


def rep_for_phone(workspace_id, phone: str) -> WorkspaceMember | None:
    for member, user in _rep_rows(workspace_id, phone):
        if user.status == "active" and user.deleted_at is None and linked_phone(member, user) == phone:
            return member
    return None


def _member_for_code(workspace_id, code: str) -> WorkspaceMember | None:
    m = db.session.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.status == "active",
                                                 WorkspaceMember.notification_prefs[PREFS_KEY]["code"].astext == code).first()
    if m is None:
        return None
    exp = prefs(m).get("code_expires_at")
    return m if exp and dt.datetime.fromisoformat(exp) > utcnow() else None


# ---- acting as the rep -----------------------------------------------------------------------------------------------

_G_KEYS = ("user", "member", "workspace", "permissions", "features", "access", "session", "impersonator_id", "_ai_cfg", "ai_proposals")


@contextmanager
def acting_as(member: WorkspaceMember):
    """Run CRM code as this member, the way a signed-in request would: same permissions, plan features and phone masking."""
    from app.services import features as feature_service
    from app.services.access import compute_access

    ctx = None
    if not has_request_context():  # background jobs: the AI and privacy code read the member from a request context
        ctx = current_app.test_request_context()
        ctx.push()
    saved = {k: getattr(g, k) for k in _G_KEYS if hasattr(g, k)}
    try:
        user = db.session.get(User, member.user_id)
        ws = db.session.get(Workspace, member.workspace_id)
        g.user, g.member, g.workspace, g.session, g.impersonator_id = user, member, ws, None, None
        g.permissions = set(member.role.permissions)
        g.access = compute_access(ws)
        g.features = feature_service.workspace_features(ws)
        for k in ("_ai_cfg", "ai_proposals"):
            g.pop(k, None)
        with tenant_scope(ws.id):
            yield user
    finally:
        for k in _G_KEYS:
            g.pop(k, None)
        for k, v in saved.items():
            setattr(g, k, v)
        if ctx is not None:
            from app.core import tenant

            prev = tenant.current()
            ctx.pop()  # request teardown resets the tenant; keep the job's own scope
            tenant._ctx.set(prev)


def blocked_reason() -> str | None:
    """Why the current member can't use the assistant from WhatsApp, in words for the rep."""
    if g.access.state == "suspended" or not g.access.allowed:
        return "Your workspace's CRM Wala subscription needs attention, so I can't update the CRM right now. Ask your admin to check Billing."
    if "whatsapp_integration" not in g.features or "ai_assistant" not in g.features:
        return "The CRM on WhatsApp needs the WhatsApp and AI assistant features on your workspace's plan. Ask your admin to upgrade."
    if not has_permission(g.permissions, "ai.use"):
        return "Your role doesn't include the AI assistant, so I can't take updates from WhatsApp. Ask your admin to allow it."
    return None


# ---- sending to the rep ------------------------------------------------------------------------------------------------

def _origin() -> str:
    return current_app.config["WEB_ORIGIN"].rstrip("/")


def to_whatsapp(md: str) -> str:
    """The assistant writes markdown for the app; turn it into WhatsApp formatting with full links."""
    s = md or ""
    s = re.sub(r"\[([^\]]+)\]\((/[^)\s]*)\)", lambda m: f"{m.group(1)} ({_origin()}{m.group(2)})", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"*\1*", s)
    s = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", s, flags=re.M)
    s = re.sub(r"^\s*[-*]\s+", "• ", s, flags=re.M)
    return s.strip()


def _masked(text: str) -> str:
    return privacy.mask_text(text)


def _record_out(i: Integration, phone: str, user_id, wamid: str, kind: str, body: str | None, data: dict) -> WhatsAppMessage:
    m = WhatsAppMessage(workspace_id=i.workspace_id, direction="outbound", status="sent", kind=kind, phone=phone, body=body, user_id=user_id,
                        wa_message_id=wamid, data={"rep": True, **data})
    db.session.add(m)
    db.session.flush()
    return m


def send_text(i: Integration, phone: str, user_id, text: str, **data) -> WhatsAppMessage:
    body = _masked(text)[:4096]
    wamid = wa._post(i, {"to": phone, "type": "text", "text": {"body": body, "preview_url": False}})
    return _record_out(i, phone, user_id, wamid, "text", body, data)


def send_buttons(i: Integration, phone: str, user_id, text: str, buttons: list[tuple[str, str]], **data) -> WhatsAppMessage:
    body = _masked(text)
    body = body if len(body) <= 1024 else body[:1020] + "…"
    action = {"buttons": [{"type": "reply", "reply": {"id": bid, "title": title[:20]}} for bid, title in buttons[:3]]}
    wamid = wa._post(i, {"to": phone, "type": "interactive", "interactive": {"type": "button", "body": {"text": body}, "action": action}})
    return _record_out(i, phone, user_id, wamid, "interactive", body, data)


def send_alert(i: Integration, phone: str, user_id, full: str, short: str, **data) -> str:
    """Business-started message to a rep: free text inside the 24-hour window, else the admin's team alert template.
    Returns 'sent', 'template' or 'no_template'."""
    if wa.window_open(i.workspace_id, phone):
        send_text(i, phone, user_id, full, **data)
        return "sent"
    t = (i.config or {}).get("team_template")
    if not t:
        return "no_template"
    param = re.sub(r"\s+", " ", _masked(short)).strip()[:900]  # Meta rejects newlines and tabs inside template values
    names = t.get("param_names") or ["1"]
    payload = {"to": phone, "type": "template", "template": {"name": t["name"], "language": {"code": t["language"]},
                                                             "components": [{"type": "body", "parameters": wa._body_parameters(names[:1], [param])}]}}
    wamid = wa._post(i, payload)
    _record_out(i, phone, user_id, wamid, "template", wa._render(t.get("body") or "", names[:1], [param]), {**data, "template": t["name"]})
    return "template"


# ---- inbound ---------------------------------------------------------------------------------------------------------

def _plain(m: dict) -> str:
    t = m.get("type")
    if t == "text":
        return (m.get("text") or {}).get("body", "")
    if t == "button":
        return (m.get("button") or {}).get("text", "")
    return ""


def _button_id(m: dict) -> str | None:
    if m.get("type") == "interactive":
        return ((m.get("interactive") or {}).get("button_reply") or {}).get("id")
    if m.get("type") == "button":
        return (m.get("button") or {}).get("payload")
    return None


def handle_inbound(i: Integration, m: dict, phone: str) -> bool:
    """Called for every inbound WhatsApp message before client handling. True when it was a rep's message (handled here)."""
    ws_id = i.workspace_id
    member = rep_for_phone(ws_id, phone)
    text = _plain(m)
    if member is None:
        code = LINK_RE.match(text)
        member = _member_for_code(ws_id, code.group(1)) if code else None
        if member is None:
            return False  # a client (or someone we don't know): the normal flow puts it on their timeline
        _log_in(i, m, phone, member, text)
        user = db.session.get(User, member.user_id)
        if wa.normalize_phone(user.phone) != phone:
            db.session.commit()
            _safe_send(i, phone, None, "This number doesn't match the phone on your CRM Wala profile. Update your profile phone, then get a new code.")
            return True
        p = save_prefs(member, phone=phone, linked_at=utcnow().isoformat(), code=None, code_expires_at=None)
        db.session.commit()
        on = [w for w, k in (("morning plan", "morning_plan"), ("new lead alerts", "new_leads")) if p.get(k)]
        _safe_send(i, phone, user.id, f"✅ Linked, {user.name.split()[0]}! Messages from this number now update CRM Wala as you.\n\n" + HELP +
                   (f"\n\nYou'll get: {' and '.join(on)}." if on else ""))
        return True

    _log_in(i, m, phone, member, text)
    db.session.commit()  # committed before the slow part, so a Meta retry of this message is ignored
    with acting_as(member) as user:
        try:
            reason = blocked_reason()
            if reason:
                send_text(i, phone, user.id, reason)
            else:
                _handle(i, member, user, phone, m, text)
            db.session.commit()
        except ApiError as e:
            db.session.rollback()
            _safe_send(i, phone, user.id, e.message)
        except Exception:
            db.session.rollback()
            log.exception("whatsapp rep message failed")
            _safe_send(i, phone, user.id, "Sorry, something went wrong on our side and nothing was saved. Please try again in a minute.")
    return True


def _safe_send(i: Integration, phone: str, user_id, text: str) -> None:
    try:
        send_text(i, phone, user_id, text)
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.warning("couldn't reply to a rep on WhatsApp", exc_info=True)


def _log_in(i: Integration, m: dict, phone: str, member: WorkspaceMember, text: str) -> None:
    kind, label = wa._inbound_text(m)
    db.session.add(WhatsAppMessage(workspace_id=i.workspace_id, direction="inbound", status="received", kind=kind, phone=phone, body=(text or label)[:4096],
                                   user_id=member.user_id, wa_message_id=m.get("id"), data={"rep": True, "type": m.get("type")}))
    db.session.flush()


def _handle(i: Integration, member: WorkspaceMember, user: User, phone: str, m: dict, text: str) -> None:
    bid = _button_id(m)
    if bid and bid.startswith("wacrm:"):
        return _on_button(i, user, phone, bid)
    heard = None
    if m.get("type") == "audio":
        heard = text = _transcribe(i, phone, m)
        if not text:
            return
    elif m.get("type") not in ("text", "button"):
        send_text(i, phone, user.id, "I can read text messages and voice notes. Send your update as one of those.")
        return
    cmd = text.strip().lower().rstrip(".!")
    if cmd in ("help", "hi", "hello", "menu", "?", "start"):
        send_text(i, phone, user.id, HELP)
    elif cmd in ("plan", "today", "my day", "my plan", "aaj"):
        send_text(i, phone, user.id, plan_text())
    elif cmd in ("plan on", "plan off", "alerts on", "alerts off", "stop"):
        on = cmd.endswith(" on")
        keys = ("morning_plan", "new_leads") if cmd == "stop" else ("morning_plan",) if cmd.startswith("plan") else ("new_leads",)
        save_prefs(member, **{k: on for k in keys})
        what = {"morning_plan": f"morning plan at {PLAN_HOUR} AM", "new_leads": "new lead alerts"}
        send_text(i, phone, user.id, f"{'✅ Turned on' if on else '🔕 Turned off'}: {' and '.join(what[k] for k in keys)}.")
    elif cmd == "cancel":
        n = _drop_pending(user.id)
        send_text(i, phone, user.id, f"Cancelled {n} card{'s' if n != 1 else ''}. Nothing was saved." if n else "There's nothing waiting for you to confirm.")
    else:
        _understand(i, user, phone, text, heard)


def _transcribe(i: Integration, phone: str, m: dict) -> str | None:
    from app.services.ai import features, settings as ai_settings

    cfg = ai_settings.resolve()
    if not ai_settings.PROVIDERS.get(cfg.provider, {}).get("audio"):
        send_text(i, phone, g.user.id, "I can't listen to voice notes yet: your workspace needs an AI key that can transcribe audio (OpenAI). Please send the update as text.")
        return None
    audio = m.get("audio") or {}
    creds = integrations.get_creds(i)
    hdr = {"Authorization": f"Bearer {creds['access_token']}"}
    try:
        meta = httpx.get(wa._url(audio["id"]), headers=hdr, timeout=15)
        meta.raise_for_status()
        data = httpx.get(meta.json()["url"], headers=hdr, timeout=60)
        data.raise_for_status()
    except (httpx.HTTPError, KeyError, ValueError):
        raise ApiError(502, "whatsapp_media", "I couldn't download that voice note from WhatsApp. Please send it again, or type the update.")
    mime = (audio.get("mime_type") or "audio/ogg").split(";")[0]
    text = features.transcribe(data.content, "voice." + (mime.split("/")[-1] or "ogg"), mime).strip()
    if not text:
        send_text(i, phone, g.user.id, "I couldn't make out any words in that voice note. Please try again or type it.")
        return None
    return text


# ---- understanding an update -----------------------------------------------------------------------------------------

def _lead_in(text: str) -> tuple[Lead | None, list[Lead]]:
    """The lead the rep is talking about: by phone number, else by first name (plus surname when given). Returns
    (lead, []) when it's clear, (None, candidates) when several match, (None, []) when none do."""
    base = db.session.query(Lead).filter(Lead.workspace_id == g.workspace.id, Lead.deleted_at.is_(None), Lead.converted_at.is_(None))
    digits = re.sub(r"\D", "", " ".join(re.findall(r"\+?\d[\d\s-]{8,}\d", text)))
    if len(digits) >= 10:
        rows = base.filter(wa._same_number_clause(Lead.phone, digits[-10:])).limit(3).all()
        return (rows[0], []) if len(rows) == 1 else (None, rows)
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'.-]+", text)]
    names = {w for w in words if len(w) >= 3}
    if not names:
        return None, []
    rows = base.filter(func.lower(Lead.first_name).in_(names)).order_by(Lead.last_activity_at.desc().nullslast()).limit(20).all()
    if len(rows) > 1:
        full = [l for l in rows if l.last_name and any(a == l.first_name.lower() and b == l.last_name.lower() for a, b in zip(words, words[1:]))]
        mine = [l for l in (full or rows) if l.owner_id == g.user.id]
        rows = full if len(full) == 1 else mine if len(mine) == 1 else (full or rows)
    return (rows[0], []) if len(rows) == 1 else (None, rows[:4])


def _understand(i: Integration, user: User, phone: str, text: str, heard: str | None) -> None:
    from app.services.ai import actions, assistant, extract, features, settings as ai_settings
    from app.services.ai.actions import ActionError

    real_ai = ai_settings.resolve().provider != "mock"
    lead, several = _lead_in(text)
    has_phone = len(re.sub(r"\D", "", text)) >= 10
    reply, proposals = "", []
    prefix = f"🎙️ I heard: “{heard[:300]}”\n\n" if heard else ""
    if several:
        names = "\n".join(f"• {l.name}" + (f" ({' · '.join(x for x in (l.bhk, l.location, l.status) if x)})" if (l.bhk or l.location or l.status) else "") for l in several)
        send_text(i, phone, user.id, prefix + f"Which one did you mean?\n{names}\n\nSend the update again with their full name.")
        return
    try:
        if lead and (VISIT_WORDS.search(text) or CALL_WORDS.search(text)):
            kind = "visit" if VISIT_WORDS.search(text) else "call"
            proposals = [features.visit_log(lead.id, text, kind)["proposal"]]
        elif lead and not real_ai:
            actions.begin()
            now = utcnow()
            lo, hi = extract.parse_budget(text)
            fu = extract.follow_up_hint(text, now)
            changes = {k: v for k, v in (("budget_min", lo), ("budget_max", hi), ("bhk", extract.bhk(text)), ("next_follow_up_at", fu.isoformat() if fu else None)) if v}
            if changes:
                try:
                    actions.propose_update_lead({"id": str(lead.id)}, changes, reason="From your WhatsApp message")
                except ActionError:
                    pass
            actions.propose_log_note({"type": "lead", "id": str(lead.id)}, text)
            proposals = actions.collected()
        elif not lead and has_phone or NEW_LEAD.match(text):
            proposals = features.capture(NEW_LEAD.sub("", text), None, None)["proposals"][:1]
        else:
            page = {"entity": "lead", "id": str(lead.id), "label": lead.name} if lead else None
            res, proposals = assistant.ask([{"role": "user", "content": "(Sent from WhatsApp; keep the answer short.) " + text}], page)
            db.session.commit()
            reply = to_whatsapp(res.text)
    except ApiError as e:
        if e.code in ("empty", "nothing_found", "cannot_propose"):
            send_text(i, phone, user.id, prefix + e.message + "\n\nSend *help* for examples.")
            return
        raise
    cards = [p for p in proposals if p.get("ops")][:MAX_CARDS]
    if reply and (not cards or len(reply) < 600):
        send_text(i, phone, user.id, prefix + reply)
        prefix = ""
    for p in cards:
        send_card(i, phone, user.id, p, prefix)
        prefix = ""
    if not cards and not reply:
        send_text(i, phone, user.id, prefix + "I couldn't tell what to change from that. Start with the client's name, for example "
                  "“Visited Priya, liked 1502, follow up Sunday”. Send *help* for more.")


def card_text(p: dict) -> str:
    lines = [f"*{p['title']}*"]
    if p.get("description"):
        lines.append(f"_{p['description']}_")
    for c in p.get("changes") or []:
        to = c.get("display_to")
        if to in (None, "", []):
            continue
        to = ", ".join(map(str, to)) if isinstance(to, list) else str(to)
        frm = c.get("display_from")
        frm = ", ".join(map(str, frm)) if isinstance(frm, list) else frm
        lines.append(f"• {c['label']}: " + (f"{frm} → {to}" if frm not in (None, "") and str(frm) != to else to))
    if p.get("items"):
        lines.append(f"• {len(p['items'])} records")
    if p.get("warning"):
        lines.append(f"⚠️ {p['warning']}")
    lines.append("\nTap Confirm to save. Nothing is saved until you do.")
    return "\n".join(lines)


def send_card(i: Integration, phone: str, user_id, p: dict, prefix: str = "") -> WhatsAppMessage:
    return send_buttons(i, phone, user_id, prefix + card_text(p), [(f"wacrm:ok:{p['id']}", "✅ Confirm"), (f"wacrm:no:{p['id']}", "Cancel")],
                        card_id=p["id"], proposal=p, state="pending")


def _card(user_id, pid: str, lock: bool = True) -> WhatsAppMessage | None:
    q = db.session.query(WhatsAppMessage).filter(WhatsAppMessage.workspace_id == g.workspace.id, WhatsAppMessage.user_id == user_id,
                                                 WhatsAppMessage.direction == "outbound", WhatsAppMessage.data["card_id"].astext == pid)
    return (q.with_for_update() if lock else q).first()


def _set(card: WhatsAppMessage, **kw) -> None:
    card.data = {**(card.data or {}), **kw}


def _drop_pending(user_id) -> int:
    rows = db.session.query(WhatsAppMessage).filter(WhatsAppMessage.workspace_id == g.workspace.id, WhatsAppMessage.user_id == user_id,
                                                    WhatsAppMessage.direction == "outbound", WhatsAppMessage.data["state"].astext == "pending",
                                                    WhatsAppMessage.created_at > utcnow() - CARD_TTL).all()
    for r in rows:
        _set(r, state="cancelled")
    return len(rows)


def _on_button(i: Integration, user: User, phone: str, bid: str) -> None:
    _, action, pid = (bid.split(":", 2) + ["", ""])[:3]
    card = _card(user.id, pid)
    if card is None:
        send_text(i, phone, user.id, "I couldn't find that card any more. Send the update again.")
        return
    p, state = card.data["proposal"], card.data.get("state")
    if action == "undo":
        saved_at = card.data.get("saved_at")
        if state != "saved" or not saved_at or dt.datetime.fromisoformat(saved_at) < utcnow() - UNDO_TTL:
            send_text(i, phone, user.id, "It's too late to undo that here. Open the record in CRM Wala to change it.")
            return
        _set(card, state="undoing")
        db.session.commit()
        err = run_calls(user, p.get("undo") or [], {}, card.data.get("results") or [], keep_going=True)[1]
        _set(card, state="saved" if err else "undone")
        _audit(p, "undone" if not err else "failed", err)
        send_text(i, phone, user.id, f"Couldn't undo: {err}" if err else f"↩️ Undone: {p['title']}.")
        return
    if state != "pending":
        done = {"saved": "already saved", "cancelled": "cancelled", "running": "being saved", "undone": "undone", "failed": "failed earlier"}.get(state, state)
        send_text(i, phone, user.id, f"That card was {done}.")
        return
    if card.created_at < utcnow() - CARD_TTL:
        _set(card, state="expired")
        send_text(i, phone, user.id, "That card is more than a day old, so I didn't save it. Send the update again.")
        return
    if action == "no":
        _set(card, state="cancelled")
        _audit(p, "cancelled")
        send_text(i, phone, user.id, "Cancelled. Nothing was saved.")
        return
    _set(card, state="running")
    db.session.commit()  # a second tap now sees "being saved"
    values = {c["key"]: c.get("to") for c in p.get("changes") or []}
    results, err = run_calls(user, p["ops"], values, [])
    card = _card(user.id, pid)
    if err:
        if results:  # put back what did run, so a half-saved change doesn't linger
            run_calls(user, p.get("undo") or [], {}, results, keep_going=True)
        _set(card, state="failed", error=err[:300])
        _audit(p, "failed", err)
        send_text(i, phone, user.id, f"❌ Couldn't save “{p['title']}”: {err}\nNothing was changed. Fix it and send the update again.")
        return
    _set(card, state="saved", saved_at=utcnow().isoformat(), results=results)
    _audit(p, "approved")
    url = _result_url(p, results)
    text = f"✅ Saved: {p['title']}." + (f"\n{_origin()}{url}" if url else "")
    if p.get("undo") and _can_undo(p["undo"]):
        send_buttons(i, phone, user.id, text, [(f"wacrm:undo:{pid}", "↩️ Undo")])
    else:
        send_text(i, phone, user.id, text)


def _can_undo(undo: list[dict]) -> bool:
    """Undoing a creation deletes it, which some roles (sales reps) aren't allowed to do: then don't offer an Undo that would fail."""
    for op in undo:
        if op.get("method") == "DELETE":
            seg = op.get("path", "").removeprefix("/api/v1/").split("/")[0]
            if not has_permission(g.permissions, f"{'meetings' if seg == 'calls' else seg}.delete"):  # calls share the meetings permission
                return False
    return True


def _result_url(p: dict, results: list[dict]) -> str | None:
    if p.get("kind") == "create_lead" and results and results[0].get("id"):
        return f"/app/leads/{results[0]['id']}"
    url = (p.get("record") or {}).get("url") or p.get("url")
    return url if url and url.startswith("/app/") else None


def _audit(p: dict, outcome: str, error: str | None = None) -> None:
    from app.services import audit

    if outcome in ("approved", "undone", "failed"):
        audit.record(f"ai.proposal_{outcome}", summary=f"{p['title']} — {outcome} via WhatsApp" + (f" ({error})" if error else ""),
                     after={"kind": p.get("kind"), "calls": len(p.get("ops") or []), "via": "whatsapp"})
    db.session.commit()


# ---- running a confirmed card ----------------------------------------------------------------------------------------

_PH = re.compile(r"^\{\{([\w.]+)\}\}$")


def _fill(v: Any, values: dict, results: list[dict]) -> Any:
    """Same placeholders the browser fills: {{key}} from the card's values, {{result.N.field}} from earlier calls."""
    if isinstance(v, str):
        m = _PH.match(v)
        if m:
            k = m.group(1)
            if k.startswith("result."):
                _, n, f = (k.split(".") + ["", ""])[:3]
                return (results[int(n)] if n.isdigit() and int(n) < len(results) else {}).get(f)
            return values.get(k)
        return re.sub(r"\{\{result\.(\d+)\.(\w+)\}\}", lambda m: str((results[int(m.group(1))] if int(m.group(1)) < len(results) else {}).get(m.group(2)) or ""), v)
    if isinstance(v, list):
        return [_fill(x, values, results) for x in v]
    if isinstance(v, dict):
        return {k: _fill(x, values, results) for k, x in v.items()}
    return v


def _safe_path(p: str) -> bool:
    return p.startswith("/api/v1/") and ".." not in p and "//" not in p and not p.startswith("/api/v1/inbound/")


def run_calls(user: User, ops: list[dict], values: dict, results: list[dict], keep_going: bool = False) -> tuple[list[dict], str | None]:
    """Run a card's API calls as the rep, exactly as the browser would after Approve: a short-lived session for the rep,
    then each call through the app itself, so every permission check, validation, audit row and automation applies.
    Returns (results so far, first error message or None). Undo runs with keep_going, so one refused call doesn't stop the rest."""
    from app.core.auth import encode_access, start_session

    ws_id = g.workspace.id
    sess, _ = start_session(user, ws_id, ttl_days=10 / 1440)
    db.session.commit()
    token = encode_access(user, ws_id, sess.id)
    app = current_app._get_current_object()
    addr = (request.remote_addr if has_request_context() else None) or "127.0.0.1"
    out, err = list(results), None
    start = len(out)
    try:
        # A fresh app context gives the calls their own `g` and database session, like a separate request; tenant_scope puts
        # the webhook's tenant back afterwards (each request resets it when it starts).
        with tenant_scope(ws_id), app.app_context():
            client = app.test_client()
            for op in ops:
                path = _fill(op.get("path", ""), values, out)
                if not isinstance(path, str) or not _safe_path(path) or op.get("method") not in ("POST", "PATCH", "PUT", "DELETE"):
                    err = "The assistant prepared a change this app can't make."
                    break
                body = _fill(op.get("body"), values, out) if op.get("method") != "DELETE" else None
                r = client.open(path + ("&" if "?" in path else "?") + "via=whatsapp", method=op["method"], json=body,
                                headers={"Authorization": f"Bearer {token}"}, environ_base={"REMOTE_ADDR": addr})
                j = r.get_json(silent=True) or {}
                if r.status_code >= 400:
                    e = j.get("error") or {}
                    details = e.get("details")
                    err = err or (e.get("message") or f"Error {r.status_code}") + (f" ({'; '.join(f'{k}: {v}' for k, v in details.items())})" if isinstance(details, dict) and details else "")
                    if keep_going:
                        out.append({})
                        continue
                    break
                out.append(j.get("data") if isinstance(j.get("data"), dict) else {})
    finally:
        with tenant_scope(ws_id):
            s = db.session.get(type(sess), sess.id)
            if s is not None:
                s.revoked_at = utcnow()
            db.session.commit()
    return out[start:] if start else out, err


# ---- morning plan and new lead alerts ---------------------------------------------------------------------------------

def _clock(d: dt.datetime) -> str:
    from app.services.ai import actions

    return d.astimezone(actions._tz()).strftime("%I:%M %p").lstrip("0")


def plan_text(intro: str | None = None) -> str:
    from app.services.ai import features

    d = features.my_day()
    if intro is None:
        try:
            intro = features.my_day_intro()
        except ApiError:
            intro = f"Good morning {g.user.name.split()[0]}!"
    lines = [intro]
    for s in d["sections"]:
        if not s["items"]:
            continue
        lines.append(f"\n*{s['title']}*")
        for it in s["items"][:6]:
            when = f"{_clock(dt.datetime.fromisoformat(it['time']))} " if it.get("time") else ""
            lines.append(f"• {when}{it['title']}" + (f": {it['reason']}" if it.get("reason") else ""))
        if len(s["items"]) > 6:
            lines.append(f"• …and {len(s['items']) - 6} more")
    lines.append(f"\nOpen your day: {_origin()}/app/ai?tab=day\nAfter each visit or call, send me an update here.")
    return "\n".join(lines)


def plan_summary() -> str:
    from app.services.ai import features

    c = features.my_day()["counts"]
    parts = [f"{n} {label}{'' if n == 1 else 's'}" for n, label in ((c["visits"], "site visit"), (c["follow_ups"], "follow-up"), (c["new"], "new enquiry to call"),
                                                                   (c["holds"], "hold expiring"), (c["tasks"], "to-do")) if n]
    parts = [p.replace("enquirys", "enquiries") for p in parts]
    return f"Good morning {g.user.name.split()[0]}! Today: " + (", ".join(parts) if parts else "nothing urgent") + ". Reply *plan* for the full list."


def _opted(key: str):
    return db.session.query(WorkspaceMember, Integration).join(
        Integration, (Integration.workspace_id == WorkspaceMember.workspace_id) & (Integration.provider == "whatsapp")).filter(
        Integration.status.in_(("connected", "error")), WorkspaceMember.status == "active",
        WorkspaceMember.notification_prefs[PREFS_KEY][key].astext == "true", WorkspaceMember.notification_prefs[PREFS_KEY]["phone"].astext.isnot(None))


def send_morning_plans(now: dt.datetime | None = None) -> dict:
    """Every rep who opted in gets today's plan once, at PLAN_HOUR in the workspace's timezone (run every 15 minutes)."""
    from zoneinfo import ZoneInfo

    now = now or utcnow()
    stats = {"sent": 0, "template": 0, "skipped": 0, "failed": 0}
    for member_id, integration_id in [(m.id, i.id) for m, i in _opted("morning_plan").all()]:
        member, i = db.session.get(WorkspaceMember, member_id), db.session.get(Integration, integration_id)
        ws = db.session.get(Workspace, member.workspace_id)
        try:
            local = now.astimezone(ZoneInfo(ws.timezone or "Asia/Kolkata"))
        except Exception:
            local = now.astimezone(ZoneInfo("Asia/Kolkata"))
        if local.hour != PLAN_HOUR or prefs(member).get("last_plan_on") == local.date().isoformat():
            continue
        with acting_as(member) as user:
            phone = linked_phone(member, user)
            try:
                if not phone or blocked_reason():
                    stats["skipped"] += 1
                    continue
                how = send_alert(i, phone, user.id, plan_text(), plan_summary(), alert="plan")
                save_prefs(member, last_plan_on=local.date().isoformat(), last_plan_status=how)
                stats["sent" if how == "sent" else "template" if how == "template" else "skipped"] += 1
                db.session.commit()
            except Exception:
                db.session.rollback()
                stats["failed"] += 1
                log.warning("morning plan failed for member %s", member_id, exc_info=True)
    return stats


def _alert_texts(lead: Lead) -> tuple[str, str]:
    from app.services.ai import actions

    hint = " · ".join(x for x in (lead.bhk, actions.money(lead.budget_max), lead.location, lead.source and lead.source.replace("_", " ")) if x)
    phone = f"\nPhone: {lead.phone}" if lead.phone and privacy.can_view() else ""
    url = f"{_origin()}/app/leads/{lead.id}"
    full = (f"🔔 *New lead: {lead.name}*" + (f"\n{hint}" if hint else "") + phone + f"\n{url}\n\n"
            f"After you call, send me an update, e.g. “Called {lead.first_name}, visit Saturday 11 am”.")
    short = f"New lead: {lead.name}" + (f" ({hint})" if hint else "") + f". Open {url}"
    return full, short


def send_lead_alerts(now: dt.datetime | None = None) -> dict:
    """WhatsApp a rep each new lead they're given (from the in-app "new lead" notifications; run every minute)."""
    import uuid

    now = now or utcnow()
    stats = {"sent": 0, "template": 0, "skipped": 0, "failed": 0}
    rows = db.session.query(Notification.id, WorkspaceMember.id, Integration.id).join(
        WorkspaceMember, (WorkspaceMember.workspace_id == Notification.workspace_id) & (WorkspaceMember.user_id == Notification.user_id)).join(
        Integration, (Integration.workspace_id == Notification.workspace_id) & (Integration.provider == "whatsapp")).filter(
        Notification.created_at > now - dt.timedelta(hours=1), ~Notification.data.has_key("wa"),  # noqa: W601 (JSONB operator)
        # Leads assigned in the app, from the website or portals ("new_lead"), and new leads that came in on WhatsApp.
        (Notification.type == "new_lead") | ((Notification.type == "whatsapp_reply") & Notification.title.like("New WhatsApp lead%")),
        Integration.status.in_(("connected", "error")), WorkspaceMember.status == "active",
        WorkspaceMember.notification_prefs[PREFS_KEY]["new_leads"].astext == "true").limit(200).all()
    for nid, member_id, integration_id in rows:
        n, member, i = db.session.get(Notification, nid), db.session.get(WorkspaceMember, member_id), db.session.get(Integration, integration_id)
        with acting_as(member) as user:
            status = "skipped"
            try:
                m = re.search(r"/app/leads/([0-9a-f-]{36})", n.link or "")
                lead = db.session.get(Lead, uuid.UUID(m.group(1))) if m else None
                phone = linked_phone(member, user)
                if lead is not None and lead.deleted_at is None and phone and not blocked_reason():
                    status = send_alert(i, phone, user.id, *_alert_texts(lead), alert="new_lead", lead_id=str(lead.id))
            except Exception:
                db.session.rollback()
                status = "failed"
                log.warning("new lead alert failed for member %s", member_id, exc_info=True)
            n = db.session.get(Notification, nid)
            n.data = {**(n.data or {}), "wa": status}
            stats["sent" if status == "sent" else status if status in stats else "skipped"] += 1
            db.session.commit()
    return stats
