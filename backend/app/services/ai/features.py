"""The AI features behind the screens. Each one works the same way:

1. compute a deterministic answer from CRM data (always correct, free, and what basic mode returns),
2. give that plus the facts to the workspace's model to improve (better wording, reading notes and photos),
3. validate what comes back against the database before anything is shown, and turn changes into proposals.
"""
from __future__ import annotations

import datetime as dt
import re
import uuid
from collections import Counter

from flask import g
from sqlalchemy import func, or_

from app.core.errors import ApiError, bad_request, not_found
from app.extensions import db
from app.models import Call, Contact, Deal, Lead, Meeting, Note, Project, Task, Unit, User, WorkspaceMember
from app.models.base import utcnow
from app.services import inventory, reporting
from app.services.ai import actions, assistant, extract, settings as ai_settings
from app.services.ai.actions import ActionError, money

OPEN = ("new", "contacted", "qualified", "pending_review")


def _clean_lead_fields(d: dict) -> dict:
    """Keep only lead fields we understand, with the right types."""
    out: dict = {}
    for k in ("first_name", "last_name", "email", "location", "company_name", "source", "description"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[:2000 if k == "description" else 160]
    if d.get("phone"):
        out["phone"] = extract.normalize_phone(str(d["phone"]))
    if d.get("email") and not re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+$", str(d["email"])):
        out.pop("email", None)
    if d.get("intent") in ("buy", "rent", "invest", "sell", "lease"):
        out["intent"] = d["intent"]
    if d.get("property_type") in ("apartment", "villa", "plot", "office", "shop", "other"):
        out["property_type"] = d["property_type"]
    if d.get("bhk"):
        out["bhk"] = extract.bhk(str(d["bhk"])) or (str(d["bhk"])[:20] if re.search(r"\d", str(d["bhk"])) else None)
        if not out["bhk"]:
            out.pop("bhk")
    for k in ("budget_min", "budget_max"):
        v = d.get(k)
        if v not in (None, "", 0):
            try:
                n = float(v) if isinstance(v, (int, float)) else (extract.money_values(str(v)) or [None])[0]
            except (TypeError, ValueError):
                n = None
            if n and n > 0:
                out[k] = n
    if out.get("budget_min") and out.get("budget_max") and out["budget_min"] > out["budget_max"]:
        out["budget_min"], out["budget_max"] = out["budget_max"], out["budget_min"]
    return out


def find_duplicates(phone: str | None, email: str | None, exclude=None) -> list[dict]:
    if not phone and not email:
        return []
    conds = []
    digits = re.sub(r"\D", "", phone or "")[-10:]
    out = []
    for model, kind in ((Lead, "lead"), (Contact, "contact")):
        conds = []
        if len(digits) >= 7:
            conds.append(func.regexp_replace(func.coalesce(model.phone, ""), r"\D", "", "g").like(f"%{digits}"))
        if email:
            conds.append(func.lower(model.email) == email.lower())
        q = db.session.query(model).filter(model.workspace_id == g.workspace.id, model.deleted_at.is_(None), or_(*conds))
        if exclude is not None and model is Lead:
            q = q.filter(Lead.id != exclude)
        for r in q.limit(4):
            out.append({"type": kind, "id": str(r.id), "name": r.name, "phone": r.phone, "email": r.email, "url": f"/app/{kind}s/{r.id}",
                        "status": getattr(r, "status", None), "created_at": r.created_at.isoformat()})
    return out


# ---- 1. capture: paste / photo / voice -> lead ------------------------------------------------------------------------------

CAPTURE_PROMPT = (
    "Read this property enquiry (it may be a WhatsApp message or chat, a broker's forward, a visiting card photo, a register page or a transcribed voice note, "
    "in English, Hindi or Hinglish) and return JSON with these keys (omit unknown ones): first_name, last_name, phone, email, intent (buy|rent|invest|sell|lease), "
    "property_type (apartment|villa|plot|office|shop|other), bhk (like '3 BHK'), budget_min, budget_max (numbers in rupees: 1.2 Cr = 12000000, 85 lakh = 8500000; "
    "for rent use monthly rent), location (preferred area), project (project name if one is mentioned), company_name, source (99acres|magicbricks|housing|walk_in|referral|"
    "broker|facebook_ads|instagram|website|other, only if stated), description (1-3 short lines: timeline, must-haves, anything else useful). "
    "If several people appear, pick the buyer/tenant, not the broker or our own agent."
)


def capture(text: str | None, images: list[dict] | None, source: str | None = None) -> dict:
    assistant.require_feature("capture")
    text = (text or "").strip()
    if not text and not images:
        raise bad_request("Paste a message, add a photo or record a voice note first.", "empty")
    cfg = ai_settings.resolve()
    if images and cfg.provider == "mock":
        raise ApiError(400, "ai_key_needed", "Reading photos needs your workspace's own AI key. An admin can connect one in Settings → AI assistant.")
    base = extract.lead_from_text(text)
    if base and text:
        base["description"] = text[:600] if len(text) < 600 else text[:600] + "…"
    data = assistant.structured("capture", CAPTURE_PROMPT + (f"\n\nText:\n{text}" if text else "\n\n(See the attached photo.)"), {"fallback": base}, "capture",
                                tier="smart" if images else "fast", images=images)
    fields = _clean_lead_fields(data)
    if source and not fields.get("source"):
        fields["source"] = source
    if data.get("project"):
        try:
            fields["project"] = actions.find_project(data["project"]).name
        except ActionError:
            pass
    if not fields:
        raise bad_request("I couldn't find any lead details in that. Try adding the name, phone number or requirement.", "nothing_found")
    dups = find_duplicates(fields.get("phone"), fields.get("email"))
    actions.begin()
    out = {"fields": fields, "duplicates": dups}
    try:
        actions.propose_create_lead(fields, reason="From what you pasted" if text else "From the photo", duplicates=dups)
        lead_dup = next((d for d in dups if d["type"] == "lead"), None)
        if lead_dup:
            merge = {k: v for k, v in fields.items() if k not in ("first_name", "last_name", "phone", "email", "source")}
            if merge:
                try:
                    actions.propose_update_lead(lead_dup["id"], merge, reason=f"Or update the existing lead {lead_dup['name']} instead")
                except ActionError:
                    pass
    except ActionError as e:
        raise bad_request(str(e), "cannot_propose")
    db.session.commit()
    out["proposals"] = actions.collected()
    return out


def transcribe(audio: bytes, filename: str, mime: str) -> str:
    from app.services.ai.providers import get_provider

    cfg = ai_settings.resolve()
    if not ai_settings.PROVIDERS.get(cfg.provider, {}).get("audio"):
        raise ApiError(400, "ai_audio_unsupported", "Turning audio files into text needs an OpenAI key. You can still press the mic and speak — your browser types it for you.")
    assistant.meter("transcribe")
    p = get_provider("fast")
    res = p.transcribe(audio, filename, mime)  # type: ignore[attr-defined]
    assistant.record_usage("transcribe", res, p.name)
    db.session.commit()
    return res.text


# ---- 2. voice log after a visit / call -------------------------------------------------------------------------------------

VISIT_PROMPT = (
    "An agent just described a {kind} with this client (dictated, may be Hinglish). Using the lead's current details, return JSON: "
    "note (a clean 1-4 line summary for the CRM, in English), outcome (connected|no_answer|follow_up_required|interested|not_interested), "
    "flats_seen (list of flat numbers mentioned), liked_flat (number or null), status (new lead status key from {statuses} or null if unchanged), "
    "changes (only lead fields that should change: budget_min, budget_max (rupees), bhk, intent, property_type, location), "
    "next_follow_up_at (ISO local time or null; e.g. 'wife will visit Sunday' -> Sunday 11:00), follow_up_reason (short), "
    "whatsapp_message (a short warm thank-you/next-step message to the client in the language they likely use, signed with the agent's first name, no placeholders)."
)


def visit_log(lead_id: uuid.UUID, text: str, kind: str = "visit", when: str | None = None) -> dict:
    assistant.require_feature("visit_log")
    lead = db.session.query(Lead).filter(Lead.id == lead_id, Lead.workspace_id == g.workspace.id, Lead.deleted_at.is_(None)).first()
    if lead is None:
        raise not_found("Lead")
    text = (text or "").strip()
    if len(text) < 4:
        raise bad_request("Say or type what happened first.", "empty")
    now = utcnow()
    lo, hi = extract.parse_budget(text)
    seen = list(dict.fromkeys(re.findall(r"\b(\d{3,4})\b", text)))
    fu = extract.follow_up_hint(text, now)
    neg = bool(re.search(r"not interested|didn'?t like|no interest|rejected|nahi chahiye", text, re.I))
    fallback = {
        "note": text[:1000], "outcome": "not_interested" if neg else "interested" if re.search(r"liked|interested|pasand", text, re.I) else "connected",
        "flats_seen": seen, "liked_flat": None, "status": "unqualified" if neg else ("qualified" if lead.status in ("new", "contacted") and kind == "visit" else None),
        "changes": {k: v for k, v in (("budget_min", lo), ("budget_max", hi), ("bhk", extract.bhk(text))) if v},
        "next_follow_up_at": fu.isoformat() if fu else None, "follow_up_reason": "Follow up after the " + ("site visit" if kind == "visit" else "call"),
        "whatsapp_message": f"Hi {lead.first_name}, thank you for your time today{' at the site' if kind == 'visit' else ''}. "
                            f"I'll share the details we discussed shortly. Do let me know if you have any questions. – {g.user.name.split()[0]}",
    }
    statuses = [s["key"] for s in (g.workspace.settings or {}).get("lead_statuses", []) if s["key"] != "converted"]
    lead_ctx = {"name": lead.name, "status": lead.status, "intent": lead.intent, "bhk": lead.bhk, "budget_min": lead.budget_min, "budget_max": lead.budget_max,
                "location": lead.location, "project": db.session.get(Project, lead.project_id).name if lead.project_id else None}
    prompt = VISIT_PROMPT.format(kind="site visit" if kind == "visit" else "phone call", statuses=", ".join(statuses)) + "\n" + assistant.now_line() + \
        f"\nAgent: {g.user.name}\nLead: {assistant.ctx(lead_ctx)}\n\nWhat the agent said:\n{text}"
    data = assistant.structured("visit_log", prompt, {"fallback": fallback}, "visit_log", tier="smart")

    when_dt = actions.parse_when(when) if when else now
    rows: list[dict] = []
    ops: list[dict] = []
    undo: list[dict] = []
    note = (data.get("note") or text)[:5000]
    project = db.session.get(Project, lead.project_id) if lead.project_id else None
    liked = None
    flats = [str(f) for f in (data.get("flats_seen") or []) if re.fullmatch(r"\d{3,4}", str(f))]
    if data.get("liked_flat") and re.fullmatch(r"\d{3,4}", str(data["liked_flat"])):
        try:
            liked = actions.find_unit(str(data["liked_flat"]), project.name if project else None)
        except ActionError:
            liked = None
    if kind == "visit":
        vrows, body = actions.visit_op(lead, when_dt - dt.timedelta(minutes=45) if not when else when_dt, 45, project, liked, "completed",
                                       note + (f"\nFlats seen: {', '.join(flats)}" if flats else ""), None)
        rows += vrows
        ops.append({"method": "POST", "path": "/api/v1/meetings", "body": body})
        undo.append({"method": "DELETE", "path": "/api/v1/meetings/{{result.%d.id}}" % (len(ops) - 1)})
    else:
        oc = data.get("outcome") if data.get("outcome") in [o[0] for o in actions.CALL_OUTCOMES] else "connected"
        rows.append(actions.change("call_outcome", "Call outcome", None, oc, input="select", options=actions.CALL_OUTCOMES, display_to=dict(actions.CALL_OUTCOMES)[oc]))
        ops.append({"method": "POST", "path": "/api/v1/calls", "body": {"direction": "outbound", "status": "completed", "outcome": "{{call_outcome}}", "notes": "{{note}}",
                                                                        "occurred_at": when_dt.isoformat(), "lead_id": str(lead.id), "phone": lead.phone}})
        undo.append({"method": "DELETE", "path": "/api/v1/calls/{{result.%d.id}}" % (len(ops) - 1)})
    rows.append(actions.change("note", "Note", None, note, input="textarea"))
    if kind == "visit":
        ops.append({"method": "POST", "path": "/api/v1/notes", "body": {"body": "{{note}}", "lead_id": str(lead.id)}})
        undo.append({"method": "DELETE", "path": "/api/v1/notes/{{result.%d.id}}" % (len(ops) - 1)})
    changes = dict(_clean_lead_fields(data.get("changes") or {}))
    if data.get("status") and data["status"] != lead.status:
        changes["status"] = data["status"]
    if data.get("next_follow_up_at"):
        changes["next_follow_up_at"] = data["next_follow_up_at"]
    if liked and not lead.unit_id:
        changes["unit"] = str(liked.id)
    try:
        lrows, lbody, lundo = actions._lead_changes(lead, changes)
    except ActionError:
        changes.pop("status", None)
        lrows, lbody, lundo = actions._lead_changes(lead, changes)
    if kind == "visit":
        lbody["last_contacted_at"] = when_dt.isoformat()
        lundo["last_contacted_at"] = lead.last_contacted_at.isoformat() if lead.last_contacted_at else None
    if lbody:
        rows += lrows
        ops.append({"method": "PATCH", "path": f"/api/v1/leads/{lead.id}", "body": lbody})
        undo.append({"method": "PATCH", "path": f"/api/v1/leads/{lead.id}", "body": lundo})
    actions.begin()
    p = actions.proposal("visit_log", f"Log {'site visit' if kind == 'visit' else 'call'} with {lead.name}", record=actions.lead_ref(lead), changes=rows, ops=ops,
                         undo=list(reversed(undo)), description=data.get("follow_up_reason"))
    msg = (data.get("whatsapp_message") or fallback["whatsapp_message"]).strip()
    db.session.commit()
    return {"proposal": p, "whatsapp_message": msg, "phone": lead.phone}


# ---- 3. smart matching -----------------------------------------------------------------------------------------------------

def _notes_text(lead: Lead) -> str:
    notes = db.session.query(Note.body).filter(Note.workspace_id == g.workspace.id, Note.lead_id == lead.id, Note.deleted_at.is_(None)).order_by(Note.created_at.desc()).limit(6).all()
    calls = db.session.query(Call.notes).filter(Call.workspace_id == g.workspace.id, Call.lead_id == lead.id, Call.notes.isnot(None)).order_by(Call.created_at.desc()).limit(4).all()
    return "\n".join([lead.description or ""] + [n for (n,) in notes] + [c for (c,) in calls]).strip()[:4000]


def _unit_facts(u: Unit, labels: dict) -> dict:
    return {"id": str(u.id), "label": labels.get(u.id, u.name), "bhk": u.bhk, "area_sqft": float(u.area_sqft) if u.area_sqft else None, "floor": u.floor, "facing": u.facing,
            "status": u.status, "sale_price": float(u.sale_price) if u.sale_price else None, "monthly_rent": float(u.monthly_rent) if u.monthly_rent else None, "notes": u.notes}


PREF_WORDS = {"east": "east facing", "north": "north facing", "vastu": "Vastu", "ground": "ground floor", "high floor": "high floor", "low floor": "low floor",
              "lower floor": "low floor", "park": "park facing", "school": "near a school", "metro": "near the metro", "corner": "corner flat", "balcony": "balcony"}


def smart_matches(lead_id: uuid.UUID) -> dict:
    assistant.require_feature("matching")
    from app.api.v1.units import unit_res

    lead = db.session.query(Lead).filter(Lead.id == lead_id, Lead.workspace_id == g.workspace.id, Lead.deleted_at.is_(None)).first()
    if lead is None:
        raise not_found("Lead")
    cands = inventory.matching_units(lead, limit=15)
    if not cands:
        return {"picks": [], "message": None, "preferences": [], "explanation": "No available flat fits this lead's size and budget right now."}
    labels, _ = inventory.labels_for({u.id for u in cands}, set())
    notes = _notes_text(lead)
    prefs = sorted({v for k, v in PREF_WORDS.items() if re.search(rf"\b{k}", notes, re.I)})

    def pref_bonus(u: Unit) -> tuple[int, list[str]]:
        b, why = 0, []
        if "east facing" in prefs and (u.facing or "").lower().startswith("east"):
            b, why = b + 15, why + ["east facing"]
        if "north facing" in prefs and (u.facing or "").lower().startswith("north"):
            b, why = b + 15, why + ["north facing"]
        if re.search(r"not (?:on )?(?:the )?ground|no ground", notes, re.I) and u.floor == 0:
            b -= 40
        if "high floor" in prefs and u.floor >= 8:
            b, why = b + 10, why + [f"floor {u.floor}"]
        if "low floor" in prefs and 1 <= u.floor <= 4:
            b, why = b + 10, why + [f"floor {u.floor}"]
        return b, why

    ranked = sorted(cands, key=lambda u: -(u._match["score"] + pref_bonus(u)[0]))  # type: ignore[attr-defined]
    fb_picks = []
    for u in ranked[:3]:
        reasons = [*u._match["reasons"], *pref_bonus(u)[1]]  # type: ignore[attr-defined]
        price = money(u.monthly_rent if lead.intent == "rent" else u.sale_price)
        fb_picks.append({"unit_id": str(u.id), "reason": ", ".join(dict.fromkeys(r for r in [*reasons, price and f"{price}"] if r)).capitalize() or "Fits the requirement"})
    lines = [f"{i + 1}. {labels.get(u.id, u.name)} – {u.bhk or ''} {('· ' + str(int(u.area_sqft)) + ' sq ft') if u.area_sqft else ''} · "
             f"{money(u.monthly_rent if lead.intent == 'rent' else u.sale_price) or 'price on request'}".replace("  ", " ") for i, u in enumerate(ranked[:3])]
    fb_msg = f"Hi {lead.first_name}, here are {len(lines)} options that match what you're looking for:\n" + "\n".join(lines) + \
        f"\n\nShall I book a site visit? – {g.user.name.split()[0]}"
    facts = {"lead": {"name": lead.first_name, "intent": lead.intent, "bhk": lead.bhk, "budget_min": lead.budget_min, "budget_max": lead.budget_max,
                      "preferred_area": lead.location, "notes": notes},
             "candidates": [{**_unit_facts(u, labels), "base_score": u._match["score"]} for u in cands]}  # type: ignore[attr-defined]
    prompt = ("Pick the best 3 flats for this client from the candidates (all already fit size and budget). Use soft preferences in their notes "
              "(facing, floor, Vastu, view, schools…). Return JSON: picks: [{unit_id, reason (one short line, why it suits THEM)}], preferences (list of preferences you found), "
              "message (a short WhatsApp message to the client listing the picks with price, in the language of their notes, signed by the agent "
              f"{g.user.name.split()[0]}).\n\n{assistant.ctx(facts)}")
    data = assistant.structured("rank_units", prompt, {"fallback": {"picks": fb_picks, "preferences": prefs, "message": fb_msg}}, "matching", tier="fast")
    by_id = {str(u.id): u for u in cands}
    picks = [p for p in (data.get("picks") or []) if isinstance(p, dict) and str(p.get("unit_id")) in by_id][:3] or fb_picks
    actions.begin()
    out = []
    serialized = {d["id"]: d for d in unit_res.serialize_many([by_id[str(p["unit_id"])] for p in picks])}
    for p in picks:
        u = by_id[str(p["unit_id"])]
        hold = None
        if u.status in inventory.AVAILABLE and actions._can("units.update"):
            try:
                actions.propose_update_unit(str(u.id), status="on_hold", hold_hours=48, lead=str(lead.id), note=f"Held for {lead.name}")
                hold = actions.collected()[-1]
            except ActionError:
                hold = None
        out.append({"unit": serialized[str(u.id)], "label": labels.get(u.id, u.name), "reason": str(p.get("reason") or "")[:240], "hold": hold})
    db.session.commit()
    return {"picks": out, "message": (data.get("message") or fb_msg)[:2000], "preferences": [str(x)[:60] for x in (data.get("preferences") or prefs)][:8], "phone": lead.phone}


def unit_leads(unit_id: uuid.UUID) -> dict:
    assistant.require_feature("matching")
    u = db.session.query(Unit).filter(Unit.id == unit_id, Unit.workspace_id == g.workspace.id, Unit.deleted_at.is_(None)).first()
    if u is None:
        raise not_found("Flat")
    rows = inventory.matching_leads(u, limit=10)
    label = actions.unit_label(u)
    price = money(u.sale_price) or money(u.monthly_rent)
    fb = f"Hi {{first_name}}, a {u.bhk or ''} flat that matches your requirement is available: {label}{' at ' + price if price else ''}. Would you like to see it this week?".replace("  ", " ")
    data = assistant.structured("unit_pitch", "Write one short WhatsApp message offering this flat to interested buyers/tenants. Use {first_name} as the only placeholder. "
                                f"Return JSON: message.\n\nFlat: {assistant.ctx(_unit_facts(u, {u.id: label}))}", {"fallback": {"message": fb}}, "matching", tier="fast")
    msg = str(data.get("message") or fb)
    if "{first_name}" not in msg:
        msg = fb
    db.session.commit()
    return {"unit": label, "message": msg, "leads": [{**r, "url": f"/app/leads/{r['id']}", "why": ", ".join(r.get("reasons") or []) or "Fits the requirement"} for r in rows]}


# ---- 4. WhatsApp helper ----------------------------------------------------------------------------------------------------

WA_PROMPT = (
    "You help a real-estate agent on WhatsApp. Given the chat (oldest first) and what the CRM knows about the client, return JSON: "
    "summary (2-3 short lines: what they want, where things stand), reply (the agent's next message: short, warm, in the SAME language and script the client uses, "
    "grounded only in the facts given; ask for missing budget / size / area / timeline one or two at a time; never promise prices or availability not in the facts), "
    "language (english|hindi|hinglish|other), hot (true if they show intent to book/pay/visit soon), signals (short list), "
    "fields (lead fields you can now fill: first_name, last_name, intent, property_type, bhk, budget_min, budget_max (rupees), location, email)."
)


def whatsapp_assist(conversation: str, lead_id: uuid.UUID | None = None, goal: str | None = None) -> dict:
    assistant.require_feature("whatsapp")
    convo = (conversation or "").strip()
    lead = None
    if lead_id:
        lead = db.session.query(Lead).filter(Lead.id == lead_id, Lead.workspace_id == g.workspace.id, Lead.deleted_at.is_(None)).first()
        if lead is None:
            raise not_found("Lead")
    if not convo and lead is None:
        raise bad_request("Paste the WhatsApp chat first.", "empty")
    msgs = extract.whatsapp_messages(convo)
    client_text = "\n".join(m["text"] for m in msgs if not lead or lead.first_name.lower() in m["sender"].lower()) if msgs else convo
    fields = extract.lead_from_text(client_text or convo)
    if lead:
        fields = {k: v for k, v in fields.items() if not getattr(lead, k, None)}
    missing = [lbl for k, lbl in (("budget_max", "budget"), ("bhk", "size (BHK)"), ("location", "preferred area")) if not (fields.get(k) or (lead and getattr(lead, k)))]
    first = (lead.first_name if lead else fields.get("first_name")) or ""
    hinglish = bool(re.search(r"\b(hai|haan|nahi|kya|ji|chahiye|bhai|aap)\b", convo, re.I))
    if missing:
        ask = " and ".join(missing[:2])
        reply = f"Namaste {first} ji, aapka {ask} bata dijiye, main best options share karta hoon." if hinglish else f"Hi {first}, could you share your {ask}? I'll send you the best options right away."
    else:
        reply = f"{first} ji, aapke liye kuch acche options hain. Kya hum is weekend site visit plan karein?" if hinglish else f"Thanks {first}! I have a few good options for you. Would you like to visit this weekend?"
    last = msgs[-3:] if msgs else []
    fb = {"summary": (" / ".join(f"{m['sender']}: {m['text'][:120]}" for m in last) or convo[:300]), "reply": reply.replace("  ", " "),
          "language": "hinglish" if hinglish else "english", "hot": bool(extract.HOT_WORDS.search(convo)),
          "signals": [m.group(0) for m in extract.HOT_WORDS.finditer(convo)][:5], "fields": fields}
    facts = {"lead": tools_lead(lead) if lead else None, "agent": g.user.name, "goal": goal}
    if lead and lead.project_id:
        facts["available_flats"] = [_unit_facts(u, inventory.labels_for({u.id}, set())[0]) for u in inventory.matching_units(lead, limit=5)]
    data = assistant.structured("whatsapp", f"{WA_PROMPT}\n\nCRM facts: {assistant.ctx(facts)}\n\nChat:\n{convo[-6000:]}", {"fallback": fb}, "whatsapp", tier="fast")
    new_fields = _clean_lead_fields(data.get("fields") or {})
    if lead:
        new_fields = {k: v for k, v in new_fields.items() if getattr(lead, k, None) in (None, "") or k in ("budget_min", "budget_max")}
    actions.begin()
    try:
        if lead and new_fields:
            actions.propose_update_lead(str(lead.id), new_fields, reason="Details from the chat")
        elif not lead and new_fields:
            dups = find_duplicates(new_fields.get("phone"), new_fields.get("email"))
            actions.propose_create_lead({**new_fields, "description": (data.get("summary") or "")[:500]}, reason="New lead from the chat", duplicates=dups)
    except ActionError:
        pass
    db.session.commit()
    return {"summary": str(data.get("summary") or fb["summary"])[:800], "reply": str(data.get("reply") or fb["reply"])[:1500], "language": data.get("language") or fb["language"],
            "hot": bool(data.get("hot")), "signals": [str(s)[:60] for s in (data.get("signals") or [])][:6], "proposals": actions.collected(),
            "phone": lead.phone if lead else new_fields.get("phone")}


def tools_lead(lead: Lead) -> dict:
    from app.services.ai import tools

    return tools.record_context("lead", str(lead.id))


# ---- 5. My day ----------------------------------------------------------------------------------------------------------------

def _wa(phone: str | None) -> str | None:
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 10:
        d = "91" + d
    return f"https://wa.me/{d}" if len(d) >= 11 else None


def _maps(project: Project | None, location: str | None) -> str | None:
    from urllib.parse import quote

    where = ", ".join(x for x in ((project.address or project.name, project.city) if project else (location,)) if x)
    return f"https://www.google.com/maps/search/?api=1&query={quote(where)}" if where else None


def _came_in(d: dt.timedelta) -> str:
    h = max(1, int(d.total_seconds() // 3600))
    return f"Came in {h}h ago" if h < 48 else f"Came in {h // 24} days ago"


def my_day(team: bool = False) -> dict:
    assistant.require_feature("briefing")
    ws, uid = g.workspace.id, (None if team else g.user.id)
    now = utcnow()
    start = reporting.day_start(now)
    end = start + dt.timedelta(days=1)
    mine = (lambda q, col: q.filter(col == uid) if uid else q)
    visits = mine(db.session.query(Meeting).filter(Meeting.workspace_id == ws, Meeting.deleted_at.is_(None), Meeting.kind == "site_visit", Meeting.status == "scheduled",
                                                   Meeting.starts_at >= start, Meeting.starts_at < end), Meeting.organizer_id).order_by(Meeting.starts_at).all()
    leads_by_id = {l.id: l for l in db.session.query(Lead).filter(Lead.id.in_({m.lead_id for m in visits if m.lead_id}))} if visits else {}
    projects = {p.id: p for p in db.session.query(Project).filter(Project.id.in_({m.project_id for m in visits if m.project_id}))} if visits else {}
    # Group visits at the same project together so the day's route makes sense, then by time.
    first_at: dict = {}
    for m in visits:
        first_at.setdefault(m.project_id, m.starts_at)
    visits.sort(key=lambda m: (first_at[m.project_id], m.starts_at))
    follow = mine(db.session.query(Lead).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.status.in_(OPEN), Lead.next_follow_up_at < end),
                  Lead.owner_id).order_by(Lead.next_follow_up_at).limit(25).all()
    cooling = mine(db.session.query(Lead).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.status.in_(("contacted", "qualified")), Lead.score >= 50,
                                                 or_(Lead.last_contacted_at < now - dt.timedelta(days=5), Lead.last_contacted_at.is_(None))), Lead.owner_id
                   ).order_by(Lead.score.desc()).limit(8).all()
    fresh = mine(db.session.query(Lead).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.status.in_(("new", "pending_review")), Lead.last_contacted_at.is_(None),
                                               Lead.created_at < now - dt.timedelta(hours=1)), Lead.owner_id).order_by(Lead.created_at).limit(8).all()
    holds = mine(db.session.query(Unit).filter(Unit.workspace_id == ws, Unit.deleted_at.is_(None), Unit.status == "on_hold", Unit.hold_until.isnot(None),
                                               Unit.hold_until < now + dt.timedelta(hours=24)), Unit.held_by).order_by(Unit.hold_until).limit(8).all()
    overdue = mine(db.session.query(Task).filter(Task.workspace_id == ws, Task.deleted_at.is_(None), Task.status != "completed", Task.due_at < end),
                   Task.assignee_id).order_by(Task.due_at).limit(10).all()
    hold_labels, _ = inventory.labels_for({u.id for u in holds}, set())
    hold_leads = {l.id: l for l in db.session.query(Lead).filter(Lead.id.in_({u.hold_lead_id for u in holds if u.hold_lead_id}))} if holds else {}

    def lead_item(l: Lead, reason: str) -> dict:
        return {"id": str(l.id), "title": l.name, "reason": reason, "url": f"/app/leads/{l.id}", "phone": l.phone, "whatsapp": _wa(l.phone),
                "hint": " · ".join(x for x in (l.bhk, money(l.budget_max), l.location) if x)}

    sections = [
        {"key": "visits", "title": "Site visits today", "items": [{
            "id": str(m.id), "title": m.title, "time": m.starts_at.isoformat(), "reason": projects[m.project_id].name if m.project_id in projects else (m.location or ""),
            "url": f"/app/leads/{m.lead_id}" if m.lead_id else "/app/calendar", "phone": leads_by_id[m.lead_id].phone if m.lead_id in leads_by_id else None,
            "whatsapp": _wa(leads_by_id[m.lead_id].phone) if m.lead_id in leads_by_id else None, "lead_id": str(m.lead_id) if m.lead_id else None,
            "maps": _maps(projects.get(m.project_id), m.location)} for m in visits]},
        {"key": "follow_ups", "title": "Follow-ups due", "items": [lead_item(l, ("Overdue since " if l.next_follow_up_at < start else "Due ") + actions.when_label(l.next_follow_up_at))
                                                                   for l in follow]},
        {"key": "new", "title": "New enquiries not called yet", "items": [lead_item(l, _came_in(now - l.created_at) + (f" from {l.source}" if l.source else ""))
                                                                          for l in fresh]},
        {"key": "cooling", "title": "Hot leads going cold", "items": [lead_item(l, f"Score {l.score}, " + (f"no contact for {(now - l.last_contacted_at).days} days" if l.last_contacted_at else "never contacted"))
                                                                      for l in cooling]},
        {"key": "holds", "title": "Holds expiring", "items": [{"id": str(u.id), "title": hold_labels.get(u.id, u.name), "reason": "Hold ends " + actions.when_label(u.hold_until) +
                                                               (f" · for {hold_leads[u.hold_lead_id].name}" if u.hold_lead_id in hold_leads else ""),
                                                               "url": f"/app/projects/{u.project_id}?tower={u.tower_id}&unit={u.id}", "unit_id": str(u.id),
                                                               "phone": hold_leads[u.hold_lead_id].phone if u.hold_lead_id in hold_leads else None} for u in holds]},
        {"key": "tasks", "title": "To-dos due", "items": [{"id": str(t.id), "title": t.title, "reason": ("Overdue · " if t.due_at < start else "") + (actions.when_label(t.due_at) or ""),
                                                          "url": "/app/tasks", "task_id": str(t.id)} for t in overdue]},
    ]
    out = {"sections": sections, "counts": {s["key"]: len(s["items"]) for s in sections}, "date": start.isoformat()}
    if team and actions._can("reports.read"):
        out["team"] = team_stats(7)
    return out


def my_day_intro(team: bool = False) -> str:
    d = my_day(team)
    c = d["counts"]
    parts = [f"{c['visits']} site visit{'s' if c['visits'] != 1 else ''}" if c["visits"] else None, f"{c['follow_ups']} follow-up{'s' if c['follow_ups'] != 1 else ''}" if c["follow_ups"] else None,
             f"{c['new']} new enquir{'ies' if c['new'] != 1 else 'y'} to call" if c["new"] else None, f"{c['holds']} hold{'s' if c['holds'] != 1 else ''} expiring" if c["holds"] else None]
    parts = [p for p in parts if p]
    first_name = g.user.name.split()[0]
    fb = (f"Good morning {first_name}! Today you have " + ", ".join(parts) + "." + (" Start with the new enquiries — fast replies win deals." if c["new"] else "")) if parts else \
        f"Good morning {first_name}! Nothing urgent today — a good day to call warm leads and share new inventory."
    facts = {s["title"]: [{"title": i["title"], "reason": i.get("reason")} for i in s["items"][:5]] for s in d["sections"]}
    res = assistant.generate("my_day", "Write a 2-3 sentence morning briefing for this agent: what matters most today and the first thing to do. Plain text, no lists, "
                             f"friendly. Their name is {first_name}.\n\n{assistant.ctx(facts)}", {"fallback": fb}, "briefing", tier="fast", max_tokens=250)
    db.session.commit()
    return res.text.strip() or fb


def team_stats(days: int = 7) -> list[dict]:
    ws = g.workspace.id
    now = utcnow()
    since = now - dt.timedelta(days=days)
    start = reporting.day_start(now)
    members = db.session.query(User.id, User.name).join(WorkspaceMember, WorkspaceMember.user_id == User.id).filter(
        WorkspaceMember.workspace_id == ws, WorkspaceMember.status == "active").all()

    def per(q, col):
        return dict(q.group_by(col).with_entities(col, func.count()).all())

    open_l = db.session.query(Lead).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.status.in_(OPEN))
    new_leads = per(db.session.query(Lead).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.created_at >= since), Lead.owner_id)
    uncontacted = per(open_l.filter(Lead.last_contacted_at.is_(None), Lead.created_at < now - dt.timedelta(hours=2)), Lead.owner_id)
    overdue = per(open_l.filter(Lead.next_follow_up_at < start), Lead.owner_id)
    visits = per(db.session.query(Meeting).filter(Meeting.workspace_id == ws, Meeting.deleted_at.is_(None), Meeting.kind == "site_visit", Meeting.starts_at >= since,
                                                   Meeting.starts_at < now), Meeting.organizer_id)
    visits_today = per(db.session.query(Meeting).filter(Meeting.workspace_id == ws, Meeting.deleted_at.is_(None), Meeting.kind == "site_visit", Meeting.starts_at >= start,
                                                         Meeting.starts_at < start + dt.timedelta(days=1)), Meeting.organizer_id)
    won = per(db.session.query(Deal).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "won", Deal.closed_at >= since), Deal.owner_id)
    resp = dict(db.session.query(Lead.owner_id, func.percentile_cont(0.5).within_group(func.extract("epoch", Lead.last_contacted_at - Lead.created_at) / 3600)).filter(
        Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.created_at >= since, Lead.last_contacted_at.isnot(None), Lead.last_contacted_at >= Lead.created_at).group_by(Lead.owner_id).all())
    rows = [{"user_id": str(i), "name": n, "new_leads": new_leads.get(i, 0), "uncontacted": uncontacted.get(i, 0), "overdue_follow_ups": overdue.get(i, 0),
             "visits": visits.get(i, 0), "visits_today": visits_today.get(i, 0), "won": won.get(i, 0),
             "median_response_hours": round(float(resp[i]), 1) if resp.get(i) is not None else None} for i, n in members]
    return sorted(rows, key=lambda r: (-(r["uncontacted"] + r["overdue_follow_ups"]), r["name"]))


# ---- 6. Search in plain words ---------------------------------------------------------------------------------------------

LEAD_PARAMS = {
    "q": "free-text name/email search", "status": "comma-separated status keys", "source": "comma-separated sources", "owner_id": "'me' or user id",
    "intent": "buy|rent|invest|sell|lease (comma-separated)", "bhk": "comma-separated like '3 BHK'", "property_type": "apartment|villa|plot|office|shop",
    "budget_max_min": "lowest acceptable top-of-budget in rupees", "budget_max_max": "highest top-of-budget in rupees", "location": "preferred area text",
    "stale_days": "not contacted for at least N days", "follow_up": "overdue|today|upcoming|none", "score_min": "minimum score 0-100",
    "created_at_from": "YYYY-MM-DD", "created_at_to": "YYYY-MM-DD", "tags": "comma-separated tags",
}


def _search_fallback(query: str) -> dict:
    q = query.lower()
    p: dict = {}
    b = extract.bhk(query)
    if b:
        p["bhk"] = b
    it = extract.intent(query)
    if it:
        p["intent"] = it
    pt = extract.property_type(query)
    if pt and pt != "apartment":
        p["property_type"] = pt
    lo, hi = extract.parse_budget(query)
    if hi and re.search(r"under|below|upto|up to|less than|within|max|<", q):
        p["budget_max_max"] = int(hi)
    elif lo and re.search(r"above|over|more than|min|>", q):
        p["budget_max_min"] = int(lo)
    elif hi:
        p["budget_max_max"] = int(hi)
    m = re.search(r"(?:not|haven'?t been|no)\s+(?:been\s+)?(?:contacted|called|touched|spoken)[^\d]*(\d+)\s*days?", q) or re.search(r"(\d+)\+?\s*days?\s+(?:without|no)\s+contact", q)
    if m:
        p["stale_days"] = int(m.group(1))
    loc = extract.location(query)
    if loc:
        p["location"] = loc
    if re.search(r"\b(my|mine)\b", q):
        p["owner_id"] = "me"
    if "overdue" in q:
        p["follow_up"] = "overdue"
    elif re.search(r"follow.?up (?:due )?today", q):
        p["follow_up"] = "today"
    for s in ("99acres", "magicbricks", "housing", "referral", "walk_in", "website", "broker", "facebook_ads", "instagram"):
        if s.replace("_", " ") in q or s.replace("_", "-") in q:
            p["source"] = s
    statuses = {st["label"].lower(): st["key"] for st in (g.workspace.settings or {}).get("lead_statuses", [])}
    for label, key in statuses.items():
        if label in q:
            p["status"] = key
    if re.search(r"\bhot\b", q):
        p["score_min"] = 60
    if "this week" in q:
        p["created_at_from"] = (utcnow() - dt.timedelta(days=utcnow().weekday())).date().isoformat()
    elif "today" in q and "follow" not in q:
        p["created_at_from"] = utcnow().date().isoformat()
    return p


def parse_search(query: str, entity: str = "leads") -> dict:
    assistant.require_feature("search")
    if entity != "leads":
        raise bad_request("Plain-word search works on leads for now.")
    query = (query or "").strip()[:300]
    if not query:
        raise bad_request("Type what you're looking for.")
    statuses = ", ".join(f"{s['key']} ({s['label']})" for s in (g.workspace.settings or {}).get("lead_statuses", []))
    fb = _search_fallback(query)
    prompt = ("Turn this request into lead list filters. Return JSON: params (only keys from this list, string or number values), label (a short name for the view). "
              f"Allowed params: {LEAD_PARAMS}. Status keys: {statuses}. Today is {utcnow().date().isoformat()}.\n\nRequest: {query}")
    data = assistant.structured("search_filters", prompt, {"fallback": {"params": fb, "label": query[:60]}}, "search", tier="fast")
    params = {k: str(v) for k, v in (data.get("params") or {}).items() if k in LEAD_PARAMS and v not in (None, "", [])}
    if params.get("owner_id") not in (None, "me"):
        try:
            uuid.UUID(params["owner_id"])
        except ValueError:
            try:
                params["owner_id"] = str(actions.find_member(params["owner_id"]).id)
            except ActionError:
                params.pop("owner_id")
    db.session.commit()
    return {"params": params, "label": str(data.get("label") or query)[:60]}


# ---- 7. Automations by typing ------------------------------------------------------------------------------------------------

def _automation_fallback(text: str) -> dict:
    from app.services.automation import ACTIONS

    t = text.lower()
    trig = "form.submitted" if "form" in t else "deal.stage_changed" if re.search(r"deal.*(won|stage|moved)|won", t) else "deal.created" if "new deal" in t else \
        "task.completed" if "task" in t and "complete" in t else "lead.created"
    steps: list[tuple[int, dict]] = []

    def at(pat):
        m = re.search(pat, t)
        return m.start() if m else None

    if (i := at(r"assign|round.?robin|distribute")) is not None:
        steps.append((i, {"action_type": "assign_user", "config": {"strategy": "round_robin"}}))
    if (i := at(r"whatsapp")) is not None:
        if "send_whatsapp" in ACTIONS:
            steps.append((i, {"action_type": "send_whatsapp", "config": {}}))
        else:
            steps.append((i, {"action_type": "create_task", "config": {"title": "Send WhatsApp intro to {{first_name}}", "due_in_days": 0, "priority": "high"}}))
    if (i := at(r"\bemail|mail\b")) is not None:
        steps.append((i, {"action_type": "send_email", "config": {"to": "record", "subject": "Thanks for your enquiry, {{first_name}}",
                                                                   "body": "Hi {{first_name}},\n\nThank you for your interest. Our team will call you shortly with the best options.\n\nRegards,"}}))
    if (i := at(r"\b(call|task|follow.?up)\b")) is not None:
        mins = re.search(r"(\d+)\s*min", t)
        steps.append((i, {"action_type": "create_task", "config": {"title": "Call {{first_name}}", "due_in_days": 0 if mins or "today" in t else 1, "priority": "high"}}))
    for m in re.finditer(r"(?:wait|after)\s+(\d+)\s*(minute|hour|day)s?", t):
        steps.append((m.start(), {"action_type": "delay", "config": {"amount": int(m.group(1)), "unit": m.group(2) + "s"}}))
    if (m := re.search(r"tag (?:it |them |as )?[\"“']?([\w-]+)", t)):
        steps.append((m.start(), {"action_type": "add_tag", "config": {"tag": m.group(1)}}))
    if (i := at(r"notify|alert|tell (?:the )?(?:owner|manager|admin)")) is not None:
        steps.append((i, {"action_type": "send_notification", "config": {"title": "New: {{name}}", "body": "Please take a look.", "to": "admins" if "admin" in t or "manager" in t else "owner"}}))
    if (i := at(r"classif|hot or cold|broker|spam")) is not None:
        steps.append((i, {"action_type": "ai_classify_lead", "config": {}}))
    steps.sort(key=lambda s: s[0])
    return {"name": text[:60].strip().capitalize(), "description": text[:200], "trigger_type": trig, "trigger_config": {}, "steps": [s for _, s in steps] or
            [{"action_type": "create_task", "config": {"title": "Follow up with {{first_name}}", "due_in_days": 1, "priority": "medium"}}]}


def automation_draft(text: str) -> dict:
    assistant.require_feature("automations")
    from app.services.automation import ACTIONS, TRIGGERS, validate_graph

    text = (text or "").strip()[:1000]
    if len(text) < 8:
        raise bad_request("Describe what should happen, e.g. “When a 99acres lead comes in, assign it round robin and create a call task”.")
    catalogue = {"triggers": {k: v["label"] for k, v in TRIGGERS.items()}, "actions": {k: {"label": v["label"], "fields": [f["key"] + (f" ({'|'.join(f['options'])})" if f.get("options") else "")
                                                                                                                  for f in v.get("fields", [])]} for k, v in ACTIONS.items()}}
    prompt = ("Build an automation from this description. Return JSON: name, description, trigger_type, trigger_config (object), steps (ordered list of "
              "{action_type, config}). Use only these triggers and actions and their field keys; message templates may use {{first_name}}, {{name}}. "
              f"Delays use action_type 'delay' with amount and unit (minutes|hours|days).\n\nCatalogue: {assistant.ctx(catalogue)}\n\nDescription: {text}")
    data = assistant.structured("automation", prompt, {"fallback": _automation_fallback(text)}, "automations", tier="smart")
    trig = data.get("trigger_type") if data.get("trigger_type") in TRIGGERS else "lead.created"
    steps = []
    for s in (data.get("steps") or [])[:12]:
        at = s.get("action_type") if isinstance(s, dict) else None
        if at not in ACTIONS:
            continue
        keys = {f["key"]: f for f in ACTIONS[at].get("fields", [])}
        cfg = {k: v for k, v in (s.get("config") or {}).items() if k in keys}
        for k, f in keys.items():
            if k not in cfg and "default" in f:
                cfg[k] = f["default"]
            if f.get("options") and cfg.get(k) not in f["options"]:
                cfg[k] = f.get("default", f["options"][0])
        if at == "delay":
            try:
                cfg["amount"] = max(1, min(365, int(float(cfg.get("amount", 1)))))
            except (TypeError, ValueError):
                cfg["amount"] = 1
        steps.append({"id": uuid.uuid4().hex[:7], "action_type": at, "config": cfg})
    if not steps:
        raise bad_request("I couldn't turn that into steps. Mention what should happen, like assign, email, task, wait or tag.")
    nodes = [{"id": "trigger", "type": "trigger", "position": {"x": 0, "y": 0}, "data": {"trigger_type": trig, "config": data.get("trigger_config") or {}}}]
    nodes += [{"id": s["id"], "type": "action", "position": {"x": 0, "y": (i + 1) * 150}, "data": {"action_type": s["action_type"], "config": s["config"]}} for i, s in enumerate(steps)]
    graph = {"nodes": nodes, "edges": [{"id": f"e{i}", "source": nodes[i]["id"], "target": nodes[i + 1]["id"]} for i in range(len(nodes) - 1)]}
    validate_graph(graph, trig)
    db.session.commit()
    return {"name": str(data.get("name") or text[:60])[:160], "description": str(data.get("description") or text)[:400], "trigger_type": trig,
            "trigger_config": data.get("trigger_config") or {}, "graph": graph, "steps": [{"label": ACTIONS[s["action_type"]]["label"], **s} for s in steps]}


# ---- 8. AI inside automations and portal intake (no user in the loop, so they run against the workspace directly) -------------

BROKER = re.compile(r"\b(broker|channel partner|cp\b|dealer|agent here|property consultant|we have (?:inventory|options)|my client|resale inventory|commission)\b", re.I)
SPAM = re.compile(r"(https?://|bit\.ly|seo|loan offer|crypto|lottery|work from home)", re.I)


def classify_fallback(lead: Lead, text: str) -> dict:
    kind = "broker" if BROKER.search(text) else "spam" if SPAM.search(text) or (not lead.phone and not lead.email) else "genuine"
    req = sum(1 for v in (lead.bhk, lead.budget_max, lead.intent, lead.location) if v)
    temp = "hot" if extract.HOT_WORDS.search(text) or (req >= 3 and re.search(r"immediate|urgent|this month|asap|ready", text, re.I)) else "warm" if req >= 2 else "cold"
    return {"temperature": temp, "kind": kind, "reason": f"{req} of 4 requirement details given" + (", sounds like a broker" if kind == "broker" else "")}


def _auto_ai(workspace_id, kind: str, prompt: str, fallback: dict, feature: str) -> dict:
    """A structured AI call outside a user's request (automations, portal intake). Never raises: falls back to the rules."""
    from app.models import Workspace
    from app.services.ai.providers import get_provider

    try:
        cfg = ai_settings.resolve(workspace_id)
        if not cfg.enabled(feature if feature != "automation_ai" else "automations") or cfg.provider == "mock":
            return fallback
        from app.services.usage import check_limit

        check_limit(db.session.get(Workspace, workspace_id), "ai_actions_month")
        p = get_provider("fast", workspace_id, timeout=20)
        data, res = p.json(kind, assistant.SYSTEM, prompt, {"fallback": fallback})
        assistant.record_usage(feature, res, p.name, user_id=None, workspace_id=workspace_id)
        return data or fallback
    except Exception:  # an AI outage must never block a lead from arriving
        return fallback


def lead_text(lead: Lead) -> str:
    raw = (lead.custom or {}).get("portal_raw") or {}
    return "\n".join(str(x) for x in [lead.description or "", raw.get("message") if isinstance(raw, dict) else "", lead.company_name or ""] if x)


def classify_lead(lead: Lead, workspace_id) -> dict:
    text = lead_text(lead)
    fb = classify_fallback(lead, text)
    facts = {"name": lead.name, "phone_given": bool(lead.phone), "email_given": bool(lead.email), "source": lead.source, "bhk": lead.bhk, "budget_max": lead.budget_max,
             "intent": lead.intent, "location": lead.location, "message": text[:2000]}
    data = _auto_ai(workspace_id, "classify_lead", "Classify this property enquiry. Return JSON: temperature (hot|warm|cold), kind (genuine|broker|spam), reason (short). "
                    f"Brokers offer inventory or mention clients/commission.\n\n{assistant.ctx(facts)}", fb, "automation_ai")
    temp = data.get("temperature") if data.get("temperature") in ("hot", "warm", "cold") else fb["temperature"]
    kind = data.get("kind") if data.get("kind") in ("genuine", "broker", "spam") else fb["kind"]
    return {"temperature": temp, "kind": kind, "reason": str(data.get("reason") or fb["reason"])[:200]}


def extract_requirements(lead: Lead, workspace_id) -> dict:
    text = lead_text(lead)
    fb = {k: v for k, v in extract.lead_from_text(text).items() if k in ("intent", "property_type", "bhk", "budget_min", "budget_max", "location")}
    data = _auto_ai(workspace_id, "extract_requirements", CAPTURE_PROMPT + f"\n\nText:\n{text[:3000]}", fb, "automation_ai")
    fields = _clean_lead_fields(data)
    return {k: v for k, v in fields.items() if k in ("intent", "property_type", "bhk", "budget_min", "budget_max", "location") and getattr(lead, k, None) in (None, "")}


def draft_reply(lead: Lead, workspace_id, channel: str = "whatsapp") -> str:
    first = lead.first_name
    want = " ".join(x for x in (lead.bhk, {"rent": "on rent", "buy": "to buy"}.get(lead.intent or ""), f"in {lead.location}" if lead.location else "") if x)
    fb = f"Hi {first}, thank you for your enquiry{' for a ' + want if want else ''}. I'm sharing a few options that match — when is a good time for a quick call?"
    data = _auto_ai(workspace_id, "draft_reply", f"Write the first {channel} reply to this new property enquiry: short, warm, asks one useful question. Return JSON: message.\n\n"
                    f"{assistant.ctx({'name': first, 'requirement': want, 'message': lead_text(lead)[:1500]})}", {"message": fb}, "automation_ai")
    return str(data.get("message") or fb)[:1500]


def portal_cleanup(lead: Lead) -> None:
    """Run on each 99acres enquiry: fill the requirement from the message and tag brokers / spam. Rules always; AI when a key is connected."""
    cfg = ai_settings.resolve(lead.workspace_id)
    if not cfg.enabled("portal"):
        return
    fields = extract_requirements(lead, lead.workspace_id)
    for k, v in fields.items():
        setattr(lead, k, v)
    c = classify_lead(lead, lead.workspace_id)
    tags = set(lead.tags or [])
    if c["kind"] in ("broker", "spam"):
        tags.add(c["kind"])
    if c["kind"] == "genuine":
        tags.add(c["temperature"])
    lead.tags = sorted(tags)
    lead.custom = {**(lead.custom or {}), "ai_triage": c}


# ---- 9. Smart import -----------------------------------------------------------------------------------------------------------

def import_assist(entity: str, headers: list[str], rows: list[dict]) -> dict:
    assistant.require_feature("import")
    from app.services import importer

    if entity not in importer.FIELDS:
        raise bad_request("Unknown import type")
    fields = importer.FIELDS[entity]
    sample = rows[:8]
    fb = importer.suggest_mapping(entity, headers)
    prompt = ("Map spreadsheet columns to CRM fields for an Indian real-estate CRM. Headers may be in Hindi/Hinglish or broker shorthand (naam, mob, config, req, "
              "area, budget). Return JSON: mapping ({field_key: exact header}), notes (one short line about anything odd). Use each header at most once.\n\n"
              f"Fields: {[(f['key'], f['label']) for f in fields]}\nHeaders: {headers}\nSample rows: {assistant.ctx(sample)}")
    data = assistant.structured("import_map", prompt, {"fallback": {"mapping": fb, "notes": ""}}, "import", tier="fast")
    keys = {f["key"] for f in fields}
    mapping, used = {}, set()
    for k, h in (data.get("mapping") or {}).items():
        if k in keys and h in headers and h not in used:
            mapping[k] = h
            used.add(h)
    mapping = mapping or fb
    db.session.commit()
    return {"mapping": mapping, "notes": str(data.get("notes") or "")[:300]}


# ---- 10. One-click data fixes ------------------------------------------------------------------------------------------------

def data_fixes() -> list[dict]:
    """Bulk proposals that tidy leads: phone formats, and requirements written in notes but missing from the fields."""
    actions.begin()
    q = db.session.query(Lead).filter(Lead.workspace_id == g.workspace.id, Lead.deleted_at.is_(None))
    phone_fix, req_fix = [], []
    for l in q.filter(Lead.phone.isnot(None)).limit(3000):
        n = extract.normalize_phone(l.phone)
        if n and n != l.phone and n.startswith("+91"):
            phone_fix.append((l, n))
    for l in q.filter(Lead.description.isnot(None), Lead.status.in_(OPEN), or_(Lead.bhk.is_(None), Lead.budget_max.is_(None), Lead.intent.is_(None))).limit(3000):
        found = {k: v for k, v in extract.lead_from_text(l.description or "").items() if k in ("bhk", "budget_min", "budget_max", "intent") and getattr(l, k) in (None, "")}
        if found:
            req_fix.append((l, found))
    out = []
    if phone_fix and actions._can("leads.update"):
        items = phone_fix[:actions.MAX_BULK]
        out.append(actions.proposal("data_fix", f"Format {len(items)} phone number{'s' if len(items) != 1 else ''}", description="Writes Indian mobiles as +91 98765 43210 so search, "
                                    "duplicates and WhatsApp links work.", ops=[{"method": "PATCH", "path": f"/api/v1/leads/{l.id}", "body": {"phone": n}} for l, n in items],
                                    undo=[{"method": "PATCH", "path": f"/api/v1/leads/{l.id}", "body": {"phone": l.phone}} for l, _ in items],
                                    items=[{"id": str(l.id), "name": l.name, "url": f"/app/leads/{l.id}", "hint": f"{l.phone} → {n}"} for l, n in items[:50]]))
    if req_fix and actions._can("leads.update"):
        items = req_fix[:actions.MAX_BULK]
        out.append(actions.proposal("data_fix", f"Fill the requirement on {len(items)} lead{'s' if len(items) != 1 else ''} from their notes",
                                    description="Budget, size and buy/rent were written in notes but the fields were empty, so matching and reports missed them.",
                                    ops=[{"method": "PATCH", "path": f"/api/v1/leads/{l.id}", "body": f} for l, f in items],
                                    undo=[{"method": "PATCH", "path": f"/api/v1/leads/{l.id}", "body": {k: None for k in f}} for l, f in items],
                                    items=[{"id": str(l.id), "name": l.name, "url": f"/app/leads/{l.id}",
                                            "hint": ", ".join(money(v) if k.startswith("budget") else str(v) for k, v in f.items())} for l, f in items[:50]]))
    return out


# ---- 11. Insights: losses, inventory, coaching --------------------------------------------------------------------------

def loss_analysis(days: int = 180) -> dict:
    assistant.require_feature("insights")
    ws = g.workspace.id
    since = utcnow() - dt.timedelta(days=days)
    lost_leads = db.session.query(Lead).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.status.in_(("lost", "unqualified")), Lead.updated_at >= since).limit(800).all()
    lost_deals = db.session.query(Deal).filter(Deal.workspace_id == ws, Deal.deleted_at.is_(None), Deal.status == "lost", Deal.updated_at >= since).limit(400).all()
    reasons = Counter((x.lost_reason or "No reason given").strip().capitalize()[:60] for x in [*lost_leads, *lost_deals])
    by_bhk = Counter(l.bhk or "Size not set" for l in lost_leads)
    by_source = Counter(l.source or "unknown" for l in lost_leads)
    projects = {p.id: p.name for p in db.session.query(Project).filter(Project.workspace_id == ws)}
    by_project = Counter(projects.get(x.project_id, "No project") for x in [*lost_leads, *lost_deals])
    total = len(lost_leads) + len(lost_deals)
    facts = {"days": days, "lost_total": total, "top_reasons": reasons.most_common(8), "by_size": by_bhk.most_common(6), "by_source": by_source.most_common(6),
             "by_project": by_project.most_common(6),
             "sample_notes": [((x.lost_reason or "") + " | " + (x.description or "")[:200]) for x in lost_leads[:25] if x.lost_reason or x.description]}
    top = reasons.most_common(1)[0] if reasons else None
    fb = f"**{total} leads and deals were lost in the last {days} days.**" + (f"\n\n- The most common reason is **{top[0]}** ({top[1]})." if top else "") + \
        ("\n- Most losses are on **" + top_project + "**." if (top_project := next((k for k, _ in by_project.most_common() if k != "No project"), None)) else "") + \
        ("\n- **" + by_bhk.most_common(1)[0][0] + "** enquiries are lost most often." if by_bhk else "") + \
        ("\n- Ask your team to always fill a lost reason; " + str(reasons.get("No reason given", 0)) + " have none." if reasons.get("No reason given") else "")
    res = assistant.generate("loss_analysis", "Explain why this real-estate team is losing leads and deals, in 3-5 markdown bullets, each with a number and a concrete fix. "
                             f"Be specific about projects, sizes and sources.\n\n{assistant.ctx(facts)}", {"fallback": fb if total else "No lost leads or deals in this period. 🎉"},
                             "insights", tier="smart", max_tokens=600)
    db.session.commit()
    return {"text": res.text, "reasons": [{"label": k, "value": v} for k, v in reasons.most_common(8)], "total": total, "days": days}


def inventory_advice() -> dict:
    assistant.require_feature("insights")
    ws = g.workspace.id
    now = utcnow()
    units = db.session.query(Unit).filter(Unit.workspace_id == ws, Unit.deleted_at.is_(None)).limit(5000).all()
    if not units:
        return {"text": "Add a project with flats to get inventory advice.", "slow": []}
    projects = {p.id: p.name for p in db.session.query(Project).filter(Project.workspace_id == ws)}
    avail = [u for u in units if u.status in inventory.AVAILABLE]
    sold90 = [u for u in units if u.status in ("sold", "rented", "booked") and u.status_changed_at and u.status_changed_at >= now - dt.timedelta(days=90)]
    demand = Counter(l.bhk for l in db.session.query(Lead.bhk).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.status.in_(OPEN), Lead.bhk.isnot(None)))
    supply = Counter(u.bhk or "?" for u in avail)
    sold_by = Counter(u.bhk or "?" for u in sold90)
    band = lambda f: "ground" if f == 0 else "low (1-4)" if f <= 4 else "mid (5-9)" if f <= 9 else "high (10+)"
    floor_sold = Counter(band(u.floor) for u in sold90)
    facing_sold = Counter(u.facing or "not set" for u in sold90)
    slow = sorted(avail, key=lambda u: u.status_changed_at or u.created_at)[:10]
    labels, _ = inventory.labels_for({u.id for u in slow}, set())
    slow_rows = [{"id": str(u.id), "label": labels.get(u.id, u.name), "days": (now - (u.status_changed_at or u.created_at)).days, "price": money(u.sale_price or u.monthly_rent),
                  "url": f"/app/projects/{u.project_id}?tower={u.tower_id}&unit={u.id}"} for u in slow]
    facts = {"available_by_size": supply.most_common(), "open_leads_wanting_size": demand.most_common(), "sold_last_90_by_size": sold_by.most_common(),
             "sold_last_90_by_floor": floor_sold.most_common(), "sold_last_90_by_facing": facing_sold.most_common(), "slowest_flats": slow_rows,
             "available_by_project": Counter(projects.get(u.project_id, "?") for u in avail).most_common()}
    lines = []
    for size, want in demand.most_common(4):
        have = supply.get(size, 0)
        if want > have * 2 and have:
            lines.append(f"- **{size}**: {want} open leads want it but only {have} are available — hold prices firm and push these first.")
        elif have > want * 2:
            lines.append(f"- **{size}**: {have} available but only {want} leads want it — consider an offer or target this size in ads.")
    if slow_rows:
        lines.append(f"- **{slow_rows[0]['label']}** has been available for {slow_rows[0]['days']} days — the longest in your stock.")
    if floor_sold:
        lines.append(f"- Floors that sold best in 90 days: **{floor_sold.most_common(1)[0][0]}**.")
    fb = "\n".join(lines) or "Your inventory and demand look balanced right now."
    res = assistant.generate("inventory_advice", "Give a sales manager 3-5 markdown bullets on which flats to push this month and why, with numbers "
                             f"(demand vs supply by size, what sold fastest, slow movers).\n\n{assistant.ctx(facts)}", {"fallback": fb}, "insights", tier="smart", max_tokens=600)
    db.session.commit()
    return {"text": res.text, "slow": slow_rows}


def coaching(days: int = 7) -> dict:
    assistant.require_feature("insights")
    rows = team_stats(days)
    tips = []
    for r in rows:
        t = []
        if r["uncontacted"]:
            t.append(f"{r['uncontacted']} new lead{'s' if r['uncontacted'] != 1 else ''} not called yet")
        if r["overdue_follow_ups"]:
            t.append(f"{r['overdue_follow_ups']} overdue follow-up{'s' if r['overdue_follow_ups'] != 1 else ''}")
        if r["median_response_hours"] and r["median_response_hours"] > 4:
            t.append(f"takes ~{r['median_response_hours']:g}h to first contact (aim for under 1h)")
        if r["visits"] == 0 and r["new_leads"] >= 3:
            t.append("no site visits this week despite new leads")
        tips.append(f"- **{r['name']}**: " + ("; ".join(t) if t else f"on track — {r['visits']} visits, {r['won']} closed") + ".")
    fb = "\n".join(tips) or "No team activity yet."
    res = assistant.generate("coaching", f"Write a weekly coaching note for a real-estate sales manager: one markdown bullet per agent with what to praise or fix, using the numbers "
                             f"(last {days} days). Then one line on the team's biggest opportunity.\n\n{assistant.ctx(rows)}", {"fallback": fb}, "insights", tier="smart", max_tokens=700)
    db.session.commit()
    return {"text": res.text, "team": rows, "days": days}


# ---- 12. Listing writer ---------------------------------------------------------------------------------------------------

def listing(kind: str, project_id: uuid.UUID | None = None, unit_id: uuid.UUID | None = None, language: str = "english", notes: str | None = None) -> dict:
    assistant.require_feature("writer")
    ws = g.workspace.id
    u = db.session.query(Unit).filter(Unit.id == unit_id, Unit.workspace_id == ws, Unit.deleted_at.is_(None)).first() if unit_id else None
    pid = u.project_id if u else project_id
    p = db.session.query(Project).filter(Project.id == pid, Project.workspace_id == ws, Project.deleted_at.is_(None)).first() if pid else None
    if p is None:
        raise not_found("Project")
    counts = inventory.summarize(inventory.counts_by(Unit.project_id, [p.id]).get(p.id, {}))
    sizes = sorted({x for (x,) in db.session.query(Unit.bhk).filter(Unit.project_id == p.id, Unit.deleted_at.is_(None), Unit.bhk.isnot(None), Unit.status.in_(inventory.AVAILABLE))})
    prices = db.session.query(func.min(Unit.sale_price), func.max(Unit.sale_price)).filter(Unit.project_id == p.id, Unit.deleted_at.is_(None), Unit.status.in_(inventory.AVAILABLE)).one()
    facts = {"project": p.name, "developer": p.developer, "city": p.city, "locality": p.locality, "sector": p.sector, "stage": p.stage, "rera": p.rera_id,
             "possession": p.possession_date.isoformat() if p.possession_date else None, "amenities": p.amenities, "description": p.description, "available_flats": counts["available"],
             "sizes_available": sizes, "price_from": money(prices[0]), "price_to": money(prices[1])}
    if u:
        facts["flat"] = _unit_facts(u, {u.id: actions.unit_label(u)})
    where = ", ".join(x for x in (p.locality or p.sector, p.city) if x)
    what = f"{u.bhk or ''} {u.kind}".strip() if u else (", ".join(sizes) or "homes")
    price = money(u.sale_price or u.monthly_rent) if u else (f"from {facts['price_from']}" if facts["price_from"] else None)
    am = ", ".join((p.amenities or [])[:5])
    fb = {
        "description": f"{p.name}{' by ' + p.developer if p.developer else ''}{' in ' + where if where else ''} offers {what}{' ' + price if price else ''}. "
                       f"{'Possession ' + facts['possession'][:7] + '. ' if facts['possession'] else ''}{'Amenities include ' + am + '. ' if am else ''}"
                       f"{'RERA: ' + p.rera_id + '.' if p.rera_id else ''}".strip(),
        "whatsapp": f"🏡 *{p.name}*{' – ' + where if where else ''}\n✅ {what}{' · ' + price if price else ''}\n" + (f"✨ {am}\n" if am else "") +
                    f"{'🔑 Possession ' + facts['possession'][:7] + chr(10) if facts['possession'] else ''}📞 Reply to book a site visit!",
        "portal": f"{what.title()} for {'rent' if u and u.monthly_rent and not u.sale_price else 'sale'} in {p.name}{', ' + where if where else ''}. " +
                  (f"{int(u.area_sqft)} sq ft, floor {u.floor}{', ' + u.facing + ' facing' if u.facing else ''}. " if u and u.area_sqft else "") +
                  (f"Price {price}. " if price else "") + (f"Amenities: {am}. " if am else "") + (f"RERA {p.rera_id}." if p.rera_id else ""),
    }
    if kind not in fb:
        raise bad_request("Choose description, whatsapp or portal.")
    guide = {"description": "a 90-130 word brochure-style description", "whatsapp": "a WhatsApp broadcast under 70 words with a few emojis and *bold* WhatsApp formatting",
             "portal": "a 99acres/MagicBricks listing description, 80-120 words, factual, no ALL CAPS"}[kind]
    res = assistant.generate("listing", f"Write {guide} in {language}. Use only these facts; don't invent amenities, prices or dates."
                             f"{' Extra instructions: ' + notes if notes else ''}\n\n{assistant.ctx(facts)}", {"fallback": fb[kind]}, "writer", tier="smart", max_tokens=500)
    db.session.commit()
    return {"text": res.text.strip(), "kind": kind}


# ---- 9. promise ledger: spot promises in chats and call notes ---------------------------------------------------------------

PROMISE_PROMPT = """You read a property sales rep's messages and notes with a buyer and list every PROMISE the rep or the company made to the buyer:
an extra discount, free or extra parking, fittings (modular kitchen, wardrobes, ACs), a possession date, a payment plan, a waived charge
(floor rise, PLC, club membership, stamp duty, maintenance), or anything else committed. Skip questions, the buyer's own requests that the
rep did not agree to, standard features of the flat, and prices merely quoted. Each source is numbered; say which source each promise came from.
Return JSON: {"promises": [{"source": <number>, "kind": "discount|parking|fittings|possession|payment_plan|waiver|other",
"title": "<short, e.g. Free covered parking / Discount of ₹2 L>", "details": "<one sentence with conditions, or empty>",
"value": <rupees it is worth, or null>, "quote": "<the exact words it came from>"}]}. Return {"promises": []} when there are none."""

_SOURCE_KIND = {"whatsapp": "WhatsApp", "call": "Call notes", "visit": "Site visit notes", "note": "Note"}


def _promise_sources(entity: str, ident, text: str | None) -> list[dict]:
    from app.models import WhatsAppMessage
    from app.services import promises as promise_svc

    if text:
        return [{"source": "note", "text": text[:6000], "user_id": g.user.id, "date": utcnow().date()}]
    leads, contacts, deals = promise_svc.group(entity, ident)
    ws = g.workspace.id

    def related(model):
        conds = [col.in_(ids) for col, ids in ((model.lead_id, leads), (model.contact_id, contacts), (model.deal_id, deals)) if ids]
        return or_(*conds) if conds else model.id.is_(None)

    out: list[dict] = []
    for m in (db.session.query(WhatsAppMessage).filter(WhatsAppMessage.workspace_id == ws, WhatsAppMessage.direction == "outbound",
                                                       WhatsAppMessage.body.isnot(None), related(WhatsAppMessage))
              .order_by(WhatsAppMessage.created_at.desc()).limit(80)):
        out.append({"source": "whatsapp", "text": m.body, "user_id": m.user_id, "date": m.created_at.date()})
    for c in (db.session.query(Call).filter(Call.workspace_id == ws, Call.deleted_at.is_(None), Call.notes.isnot(None), related(Call))
              .order_by(Call.created_at.desc()).limit(40)):
        out.append({"source": "call", "text": c.notes, "user_id": c.user_id, "date": (c.occurred_at or c.created_at).date()})
    for mt in (db.session.query(Meeting).filter(Meeting.workspace_id == ws, Meeting.deleted_at.is_(None), related(Meeting))
               .order_by(Meeting.starts_at.desc()).limit(30)):
        body = "\n".join(x for x in (mt.summary, mt.description if mt.description != mt.summary else None) if x)
        if body:
            out.append({"source": "visit" if mt.kind == "site_visit" else "note", "text": body, "user_id": mt.organizer_id, "date": mt.starts_at.date()})
    for n in (db.session.query(Note).filter(Note.workspace_id == ws, Note.deleted_at.is_(None), related(Note))
              .order_by(Note.created_at.desc()).limit(40)):
        out.append({"source": "note", "text": n.body, "user_id": n.author_id, "date": n.created_at.date()})
    return out


def _same_promise(a: dict, b: dict) -> bool:
    if a["kind"] != b["kind"]:
        return False
    wa, wb = set(re.findall(r"\w+", a["title"].lower())), set(re.findall(r"\w+", b["title"].lower()))
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.6


def promise_scan(entity: str, ident, text: str | None = None) -> dict:
    """Promises found in the buyer's WhatsApp messages, call notes, visit notes and notes (or in pasted text), as cards to confirm.
    Nothing is recorded until a person approves a card, and approving records it as waiting for a manager."""
    from app.models import Promise
    from app.services import promises as promise_svc

    assistant.require_feature("promises")
    row = promise_svc.get_record(entity, ident)
    sources = _promise_sources(entity, ident, (text or "").strip() or None)
    fallback = {"promises": [{**p, "source": i} for i, s in enumerate(sources) for p in extract.promises_from_text(s["text"])]}
    data = fallback
    if sources:
        listing = "\n".join(f"[{i}] {_SOURCE_KIND[s['source']]}, {s['date']:%d %b %Y}: {s['text'][:1200]}" for i, s in enumerate(sources))
        data = assistant.structured("promises", f"{PROMISE_PROMPT}\n\nBuyer: {row.name}\n\nSources:\n{listing[-12000:]}", {"fallback": fallback}, "promises", tier="fast")
    existing = [{"kind": p.kind, "title": p.title} for p in db.session.query(Promise).filter(
        Promise.workspace_id == g.workspace.id, Promise.deleted_at.is_(None), promise_svc.group_filter(entity, ident))]
    kinds = dict(actions.PROMISE_KINDS)
    picked: list[dict] = []
    skipped = 0
    for p in (data.get("promises") or [])[:20]:
        if not isinstance(p, dict):
            continue
        try:
            src = sources[int(p.get("source"))]
        except (TypeError, ValueError, IndexError):
            continue
        cand = {"kind": p.get("kind") if p.get("kind") in kinds else "other", "title": str(p.get("title") or "").strip()[:200],
                "details": str(p.get("details") or "").strip()[:1000] or None, "quote": str(p.get("quote") or "").strip()[:400] or None, "src": src}
        try:
            cand["value"] = float(p["value"]) if p.get("value") not in (None, "") and float(p["value"]) >= 0 else None
        except (TypeError, ValueError):
            cand["value"] = None
        if len(cand["title"]) < 2:
            continue
        if any(_same_promise(cand, e) for e in existing) or any(_same_promise(cand, x) for x in picked):
            skipped += 1
            continue
        picked.append(cand)
    actions.begin()
    member_ids = {r[0] for r in db.session.query(WorkspaceMember.user_id).filter(WorkspaceMember.workspace_id == g.workspace.id, WorkspaceMember.status == "active")}
    for c in picked[:10]:
        s = c["src"]
        try:
            actions.propose_record_promise({"type": entity, "id": str(row.id)}, c["title"], kind=c["kind"], details=c["details"], value=c["value"],
                                           promised_by=str(s["user_id"]) if s.get("user_id") in member_ids else None, source=s["source"],
                                           quote=c["quote"] or s["text"][:400], promised_on=s["date"].isoformat())
        except ActionError:
            continue
    db.session.commit()
    return {"proposals": actions.collected(), "scanned": len(sources), "already_recorded": skipped, "ai": ai_settings.resolve().provider != "mock"}
