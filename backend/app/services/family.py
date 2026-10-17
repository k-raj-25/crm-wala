"""Family and NRI mode.

In India the family buys the house, not one person. A buyer (lead, client or deal) can have family members who decide,
pay or advise: a spouse, parents, a son working in Dubai. Each member has their own language and time zone:

- Messages to them are translated into their language by the workspace's AI (when it has a key; without one the text
  goes out as typed) and can be held until 9 am where they live instead of buzzing them at night.
- NRI members see prices in AED or USD, converted at a rate the workspace owner sets (not a live feed, so the price a rep
  quotes doesn't move under them), and get the POA and NRE-account document checklist.
- Each member can get their own link: a page with the flat and its price in their currency, their checklist, and a form
  to ask for a video walkthrough at a time in their own time zone. A rep confirms the request with a meeting link.

Members' phone numbers are hidden and revealed exactly like the buyer's (app.services.privacy).
"""
from __future__ import annotations

import datetime as dt
import decimal
import secrets
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app, g, has_request_context
from sqlalchemy import or_

from app.core.errors import ApiError, not_found
from app.extensions import db
from app.models import (
    Contact, Deal, FamilyMember, FamilyMessage, Lead, Project, Unit, Walkthrough, WhatsAppMessage, Workspace,
)
from app.models.base import utcnow
from app.services import activities, privacy

RELATIONS: dict[str, str] = {
    "spouse": "Spouse", "father": "Father", "mother": "Mother", "son": "Son", "daughter": "Daughter", "brother": "Brother",
    "sister": "Sister", "father_in_law": "Father-in-law", "mother_in_law": "Mother-in-law", "son_in_law": "Son-in-law",
    "daughter_in_law": "Daughter-in-law", "other": "Family",
}
ROLES: dict[str, str] = {"decides": "Decides", "pays": "Pays", "advises": "Advises"}
# code -> (English name, name in the language itself)
LANGUAGES: dict[str, tuple[str, str]] = {
    "en": ("English", "English"), "hi": ("Hindi", "हिन्दी"), "mr": ("Marathi", "मराठी"), "gu": ("Gujarati", "ગુજરાતી"),
    "bn": ("Bengali", "বাংলা"), "pa": ("Punjabi", "ਪੰਜਾਬੀ"), "ta": ("Tamil", "தமிழ்"), "te": ("Telugu", "తెలుగు"),
    "kn": ("Kannada", "ಕನ್ನಡ"), "ml": ("Malayalam", "മലയാളം"), "or": ("Odia", "ଓଡ଼ିଆ"), "ur": ("Urdu", "اردو"),
    "ar": ("Arabic", "العربية"),
}
CURRENCIES: dict[str, str] = {"INR": "Indian rupee", "AED": "UAE dirham", "USD": "US dollar"}
FOREIGN = ("AED", "USD")
# Where Indian families' NRIs usually live; any valid IANA zone is accepted.
TIMEZONES: list[str] = [
    "Asia/Kolkata", "Asia/Dubai", "Asia/Riyadh", "Asia/Qatar", "Asia/Kuwait", "Asia/Muscat", "Asia/Bahrain", "Asia/Singapore",
    "Asia/Kuala_Lumpur", "Asia/Hong_Kong", "Asia/Tokyo", "Europe/London", "Europe/Dublin", "Europe/Berlin", "Europe/Amsterdam",
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Toronto", "America/Vancouver",
    "Australia/Sydney", "Australia/Melbourne", "Australia/Perth", "Pacific/Auckland", "Africa/Nairobi", "Africa/Johannesburg",
]
# What an NRI needs to buy property in India. Kept as general guidance, not legal advice.
CHECKLIST: list[tuple[str, str, str]] = [
    ("passport", "Passport", "Copy of the photo and address pages."),
    ("visa_oci", "Visa, OCI or PIO card", "Proof of NRI status: a work or residence visa, or an OCI card."),
    ("pan", "PAN card", "Needed for the agreement, registration and TDS. Apply from abroad if they don't have one."),
    ("overseas_address", "Overseas address proof", "A utility bill, bank statement or lease from the country they live in."),
    ("photos", "Passport-size photos", "Usually 4 to 6 for the agreement and registration."),
    ("nre_account", "NRE or NRO account details", "Payments must come from an NRE, NRO or FCNR account in India, or by inward remittance."),
    ("firc", "Remittance proof (FIRC)", "A Foreign Inward Remittance Certificate or bank letter for each payment, for repatriation later."),
    ("poa", "Power of attorney", "If someone in India signs for them: signed abroad, attested at the Indian embassy or apostilled, "
                                 "then adjudicated (stamp duty paid) in India within 3 months."),
    ("poa_holder_id", "POA holder's ID and address proof", "Aadhaar and PAN of the person signing in India."),
    ("home_loan", "NRI home loan sanction", "Only if they're taking a loan: the bank's sanction letter."),
]
CHECKLIST_KEYS = {k for k, _, _ in CHECKLIST}
QUIET_FROM, QUIET_UNTIL = 21, 9  # don't message between 9 pm and 9 am where they live
_MODELS = {"lead": Lead, "contact": Contact, "deal": Deal}


# ---- the buyer ---------------------------------------------------------------------------------------------------

def get_record(entity: str, ident) -> Lead | Contact | Deal:
    model = _MODELS.get(entity)
    if model is None:
        raise not_found("Record")
    row = db.session.query(model).filter(model.id == ident, model.workspace_id == g.workspace.id, model.deleted_at.is_(None)).one_or_none()
    if row is None:
        raise not_found(entity.capitalize())
    return row


def group(entity: str, ident, workspace_id=None) -> tuple[set, set, set]:
    """(lead ids, contact ids, deal ids) that are the same buyer as this record, so a family added on the lead is still
    there after the lead becomes a client and a deal."""
    ws = workspace_id or g.workspace.id
    leads, contacts, deals = set(), set(), set()
    if entity == "lead":
        leads.add(ident)
        lead = db.session.get(Lead, ident)
        if lead and lead.converted_contact_id:
            contacts.add(lead.converted_contact_id)
        if lead and lead.converted_deal_id:
            deals.add(lead.converted_deal_id)
        deals |= {r[0] for r in db.session.query(Deal.id).filter(Deal.workspace_id == ws, Deal.lead_id == ident, Deal.deleted_at.is_(None))}
    elif entity == "contact":
        contacts.add(ident)
        leads |= {r[0] for r in db.session.query(Lead.id).filter(Lead.workspace_id == ws, Lead.converted_contact_id == ident)}
        deals |= {r[0] for r in db.session.query(Deal.id).filter(Deal.workspace_id == ws, Deal.contact_id == ident, Deal.deleted_at.is_(None))}
    elif entity == "deal":
        deals.add(ident)
        deal = db.session.get(Deal, ident)
        if deal and deal.lead_id:
            leads.add(deal.lead_id)
        if deal and deal.contact_id:
            contacts.add(deal.contact_id)
    return leads, contacts, deals


def members_for(entity: str, ident) -> list[FamilyMember]:
    leads, contacts, deals = group(entity, ident)
    conds = [col.in_(ids) for col, ids in ((FamilyMember.lead_id, leads), (FamilyMember.contact_id, contacts), (FamilyMember.deal_id, deals)) if ids]
    return db.session.query(FamilyMember).filter(FamilyMember.workspace_id == g.workspace.id, FamilyMember.deleted_at.is_(None), or_(*conds)) \
        .order_by(FamilyMember.created_at).all()


def buyer_of(m: FamilyMember) -> tuple[str, Lead | Contact | Deal | None]:
    """The record the member was added on (the deal first: it's furthest along)."""
    for entity, ident in (("deal", m.deal_id), ("contact", m.contact_id), ("lead", m.lead_id)):
        if ident:
            return entity, db.session.get(_MODELS[entity], ident)
    return "lead", None


def links(m: FamilyMember) -> dict:
    """FK kwargs that put an event about this member on their buyer's timelines."""
    out = {"lead_id": m.lead_id, "contact_id": m.contact_id, "deal_id": m.deal_id}
    if m.contact_id and not m.lead_id:
        c = db.session.get(Contact, m.contact_id)
        out["company_id"] = c.company_id if c else None
    return out


def record_path(m: FamilyMember) -> str:
    entity, rec = buyer_of(m)
    return f"/app/{entity}s/{rec.id}" if rec else "/app/leads"


def describe(m: FamilyMember, buyer_name: str | None = None) -> str:
    """'Rohan (son of Ramesh Gupta)'."""
    entity, rec = buyer_of(m)
    of = buyer_name or (rec.name if rec else None)
    rel = RELATIONS.get(m.relation, "Family").lower()
    return f"{m.name} ({rel} of {of})" if of and m.relation != "other" else f"{m.name}{f' ({of} family)' if of else ''}"


# ---- time zones --------------------------------------------------------------------------------------------------

def zone(tz: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz or "Asia/Kolkata")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Asia/Kolkata")


def valid_timezone(tz: str) -> bool:
    try:
        ZoneInfo(tz)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def place(tz: str) -> str:
    """'Asia/Dubai' -> 'Dubai'."""
    return tz.rsplit("/", 1)[-1].replace("_", " ")


def is_quiet(local: dt.datetime) -> bool:
    return local.hour >= QUIET_FROM or local.hour < QUIET_UNTIL


def next_morning(tz: str, now: dt.datetime | None = None) -> dt.datetime:
    """The next 9 am where they live, in UTC (today's, if it's still early morning there)."""
    local = (now or utcnow()).astimezone(zone(tz))
    day = local.date() if local.hour < QUIET_UNTIL else local.date() + dt.timedelta(days=1)
    return dt.datetime.combine(day, dt.time(QUIET_UNTIL), tzinfo=zone(tz)).astimezone(dt.timezone.utc)


def local_label(when: dt.datetime, tz: str) -> str:
    """'Tue 20 Oct, 7:30 pm Dubai time'."""
    local = when.astimezone(zone(tz))
    return f"{local:%a} {local.day} {local:%b}, {local.strftime('%I:%M %p').lstrip('0').lower()} {place(tz)} time"


# ---- money -------------------------------------------------------------------------------------------------------

def rates(ws: Workspace | None = None) -> dict:
    """INR per 1 AED / USD, as the owner set them. Empty until they do: a made-up rate would quote a wrong price."""
    ws = ws or g.workspace
    raw = (ws.settings or {}).get("fx_rates") or {}
    return {c: float(raw[c]) for c in FOREIGN if raw.get(c)}


def fx_meta(ws: Workspace | None = None) -> dict:
    ws = ws or g.workspace
    raw = (ws.settings or {}).get("fx_rates") or {}
    return {"rates": rates(ws), "updated_at": raw.get("updated_at"), "updated_by": raw.get("updated_by")}


def convert(inr, currency: str, rate_map: dict) -> int | None:
    if inr in (None, 0) or currency not in rate_map:
        return None
    return int((decimal.Decimal(str(inr)) / decimal.Decimal(str(rate_map[currency]))).quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP))


def fx_text(amount: int, currency: str) -> str:
    return f"{currency} {amount:,}"


def price_lines(m: FamilyMember, ws: Workspace | None = None) -> list[dict]:
    """The prices that matter to this buyer (their flat, else their budget), in rupees and in the member's currency."""
    from app.services.comparison import inr as inr_text

    entity, rec = buyer_of(m)
    rate_map = rates(ws)
    unit = db.session.get(Unit, rec.unit_id) if rec is not None and getattr(rec, "unit_id", None) else None
    out: list[dict] = []
    if unit is not None and unit.sale_price:
        p = db.session.get(Project, unit.project_id)
        what = " · ".join(x for x in (f"Flat {unit.number}", unit.bhk, f"{int(unit.area_sqft):,} sq ft" if unit.area_sqft else None, p.name if p else None) if x)
        out.append({"label": what, "inr": float(unit.sale_price)})
    elif isinstance(rec, Deal) and rec.value and rec.currency == "INR":
        out.append({"label": rec.name, "inr": float(rec.value)})
    elif isinstance(rec, Lead) and rec.budget_max:
        out.append({"label": "Budget" + (f" ({rec.bhk})" if rec.bhk else ""), "inr": float(rec.budget_max)})
    for line in out:
        amount = convert(line["inr"], m.currency, rate_map) if m.currency in FOREIGN else None
        line.update({"inr_text": inr_text(line["inr"]), "currency": m.currency, "amount": amount,
                     "amount_text": fx_text(amount, m.currency) if amount is not None else None,
                     "rate": rate_map.get(m.currency) if m.currency in FOREIGN else None})
    return out


# ---- serialization -----------------------------------------------------------------------------------------------

def link_url(m: FamilyMember) -> str | None:
    return f"{current_app.config['WEB_ORIGIN']}/family/{m.link_token}" if m.link_token else None


def checklist_view(m: FamilyMember) -> list[dict]:
    done = m.checklist or {}
    return [{"key": k, "label": label, "hint": hint, "done": bool(done.get(k)), "done_at": (done.get(k) or {}).get("at")} for k, label, hint in CHECKLIST]


def walkthrough_view(w: Walkthrough) -> dict:
    d = w.to_dict()
    d["local_label"] = local_label(w.starts_at, w.timezone)
    return d


def serialize(members: list[FamilyMember]) -> list[dict]:
    if not members:
        return []
    ids = [m.id for m in members]
    walks: dict = {}
    for w in db.session.query(Walkthrough).filter(Walkthrough.member_id.in_(ids), Walkthrough.status != "cancelled").order_by(Walkthrough.starts_at):
        walks.setdefault(w.member_id, []).append(walkthrough_view(w))
    queued: dict = {}
    for fm in db.session.query(FamilyMessage).filter(FamilyMessage.member_id.in_(ids), FamilyMessage.status == "scheduled"):
        queued[fm.member_id] = queued.get(fm.member_id, 0) + 1
    now = utcnow()
    out = []
    for m in members:
        d = m.to_dict()
        if m.phone and not privacy.can_view():
            d["phone"], d["phone_masked"] = privacy.mask(m.phone), True
        local = now.astimezone(zone(m.timezone))
        items = checklist_view(m)
        d.update({
            "relation_label": RELATIONS.get(m.relation, "Family"), "role_label": ROLES.get(m.role, m.role),
            "language_label": LANGUAGES.get(m.language, (m.language, m.language))[0], "place": place(m.timezone),
            "local_time": local.isoformat(), "local_label": local.strftime("%I:%M %p").lstrip("0").lower(), "quiet": is_quiet(local),
            "next_morning": next_morning(m.timezone, now).isoformat(), "prices": price_lines(m),
            "checklist": items if m.is_nri else [], "checklist_done": sum(i["done"] for i in items) if m.is_nri else 0,
            "link": link_url(m), "walkthroughs": walks.get(m.id, []), "scheduled_messages": queued.get(m.id, 0),
        })
        out.append(d)
    return out


def options() -> dict:
    return {"relations": RELATIONS, "roles": ROLES, "languages": {k: {"name": a, "native": b} for k, (a, b) in LANGUAGES.items()},
            "currencies": CURRENCIES, "timezones": TIMEZONES, "checklist": [{"key": k, "label": l, "hint": h} for k, l, h in CHECKLIST]}


def new_token() -> str:
    return secrets.token_urlsafe(24)


# ---- language ----------------------------------------------------------------------------------------------------

def translate(text: str, language: str) -> dict:
    """The message in the member's language. Uses the workspace's AI when it has a key and the WhatsApp helper is on;
    otherwise (or if the AI fails) the text goes out as typed, and `ai` says which happened."""
    from app.services.ai import assistant, settings as ai_settings

    name = LANGUAGES.get(language, ("English", ""))[0]
    out = {"text": text, "language": language, "language_label": name, "ai": False}
    cfg = ai_settings.resolve()
    if cfg.provider == "mock" or not cfg.enabled("whatsapp"):
        out["note"] = "Add an AI key in Settings → AI assistant to translate messages automatically."
        return out
    try:
        data = assistant.structured(
            "translate",
            f"Translate this WhatsApp message from an Indian real-estate agent into {name}, written in {name}'s own script. "
            "Keep it warm and natural, the way a person would text a family member of their client. Keep names, flat numbers, "
            "prices, currency codes, dates, times and links exactly as they are. Return JSON: text.\n\nMessage:\n" + text[:3000],
            {"fallback": {"text": text}}, "whatsapp", tier="fast")
    except ApiError as e:  # an allowance limit or a provider error: send it as typed rather than not at all
        out["note"] = e.message
        return out
    translated = str((data or {}).get("text") or "").strip()
    if translated:
        out.update({"text": translated[:4096], "ai": True})
    return out


# ---- drafts the rep can edit, translate and send -----------------------------------------------------------------

def draft(m: FamilyMember, kind: str) -> str:
    first = m.name.split(" ")[0]
    sender = g.user.name.split(" ")[0] if has_request_context() and getattr(g, "user", None) else ""
    sign = f"\n\n{sender}" if sender else ""
    if kind == "prices":
        lines = price_lines(m)
        if not lines:
            return f"Hi {first}, I'll share the latest prices with you shortly.{sign}"
        body = "\n".join(f"• {p['label']}: {p['inr_text']}" + (f" (about {p['amount_text']})" if p["amount_text"] else "") for p in lines)
        rate = next((p["rate"] for p in lines if p["rate"]), None)
        note = f"\n\n{m.currency} amounts are approximate, at ₹{rate:g} per {m.currency}." if rate else ""
        return f"Hi {first}, here are the prices we discussed:\n{body}{note}{sign}"
    if kind == "checklist":
        todo = [i for i in checklist_view(m) if not i["done"] and i["key"] != "home_loan"]
        body = "\n".join(f"• {i['label']}" for i in todo) or "• Nothing more, we have everything. Thank you!"
        return f"Hi {first}, for the booking from abroad we'll need these documents:\n{body}\n\nPlease share clear scans here whenever convenient.{sign}"
    if kind == "link":
        return f"Hi {first}, here is your page for the flat: prices in {m.currency}, the documents we need, and a button to book a video walkthrough " \
               f"at a time that suits you.\n{link_url(m) or ''}{sign}"
    return f"Hi {first}, "


# ---- WhatsApp ------------------------------------------------------------------------------------------------------

def deliver(fm: FamilyMessage) -> WhatsAppMessage:
    """Send one queued message now. Raises ApiError when WhatsApp says no (window closed, not connected, no number)."""
    from app.services import whatsapp

    m = db.session.get(FamilyMember, fm.member_id)
    i = whatsapp.connection(fm.workspace_id)
    phone = whatsapp.normalize_phone(m.phone)
    if not phone:
        raise ApiError(422, "validation_error", f"{m.name} doesn't have a valid mobile number.", {"phone": "Add a mobile number first"})
    t = fm.template
    if t:
        params = [str(p)[:1000] for p in t.get("params") or []]
        names = t.get("param_names") or [str(n + 1) for n in range(len(params))]
        comps = [{"type": "body", "parameters": whatsapp._body_parameters(names, params)}] if params else []
        payload = {"to": phone, "type": "template", "template": {"name": t["name"], "language": {"code": t["language"]}, **({"components": comps} if comps else {})}}
    else:
        if not whatsapp.window_open(fm.workspace_id, phone):
            raise ApiError(409, "whatsapp_window_closed", f"{m.name} hasn't messaged you in the last 24 hours, so WhatsApp only allows an approved template.")
        payload = {"to": phone, "type": "text", "text": {"body": fm.body[:4096], "preview_url": True}}
    wamid = whatsapp._post(i, payload)
    # No lead/contact link on the message itself: the buyer's WhatsApp tab is their own chat. The timeline gets an activity.
    wm = WhatsAppMessage(workspace_id=fm.workspace_id, direction="outbound", status="sent", kind="template" if t else "text", phone=phone, body=fm.body[:4096],
                         template_name=t["name"] if t else None, template_language=t.get("language") if t else None, user_id=fm.user_id, wa_message_id=wamid,
                         data={"family_member_id": str(m.id), **({"params": t.get("params")} if t else {})})
    db.session.add(wm)
    db.session.flush()
    fm.status, fm.sent_at, fm.whatsapp_message_id, fm.error = "sent", utcnow(), wm.id, None
    lang = f" in {LANGUAGES[fm.language][0]}" if fm.original and fm.language in LANGUAGES and fm.language != "en" else ""
    activities.log_activity("whatsapp", f"WhatsApp sent to {describe(m)}{lang}", workspace_id=fm.workspace_id, user_id=fm.user_id, body=fm.body[:2000],
                            data={"whatsapp_message_id": str(wm.id), "direction": "outbound", "family_member_id": str(m.id), "original": fm.original}, **links(m))
    return wm


def send_due() -> dict:
    """Send the held messages whose time has come (every minute, from the job queue). A failure is kept with its reason
    and the rep who wrote it is told."""
    from app.core.tenant import tenant_scope
    from app.services.notifications import notify

    due = [(m.id, m.workspace_id) for m in db.session.query(FamilyMessage).filter(FamilyMessage.status == "scheduled", FamilyMessage.send_at <= utcnow()).limit(200)]
    sent = failed = 0
    for mid, wid in due:
        with tenant_scope(wid):
            fm = db.session.get(FamilyMessage, mid)
            try:
                with db.session.begin_nested():
                    deliver(fm)
                sent += 1
            except ApiError as e:
                fm.status, fm.error = "failed", e.message[:400]
                member = db.session.get(FamilyMember, fm.member_id)
                notify(wid, [fm.user_id], "system", f"Couldn't send the WhatsApp to {member.name}", e.message, record_path(member))
                failed += 1
            db.session.commit()
    return {"sent": sent, "failed": failed}


def find_by_phone(workspace_id, phone: str) -> FamilyMember | None:
    from app.services.whatsapp import _same_number_clause

    return db.session.query(FamilyMember).filter(FamilyMember.workspace_id == workspace_id, FamilyMember.deleted_at.is_(None),
                                                 _same_number_clause(FamilyMember.phone, phone)).order_by(FamilyMember.updated_at.desc()).first()


def receive(workspace_id, phone: str, kind: str, text: str, wamid: str, raw: dict, profile_name: str | None, when: dt.datetime) -> bool:
    """A WhatsApp message from a family member's number: log it on their buyer instead of creating a new lead."""
    m = find_by_phone(workspace_id, phone)
    if m is None:
        return False
    from app.services import notifications

    ctx = (raw.get("context") or {}).get("id")
    wm = WhatsAppMessage(workspace_id=workspace_id, direction="inbound", status="received", kind=kind, phone=phone, body=text[:4096], wa_message_id=wamid,
                         data={"type": raw.get("type"), "profile_name": profile_name, "family_member_id": str(m.id), **({"reply_to": ctx} if ctx else {})})
    db.session.add(wm)
    db.session.flush()
    who = describe(m)
    activities.log_activity("whatsapp", f"WhatsApp reply from {who}", workspace_id=workspace_id, body=text[:2000], user_id=None, occurred_at=when,
                            data={"whatsapp_message_id": str(wm.id), "direction": "inbound", "family_member_id": str(m.id)}, **links(m))
    entity, rec = buyer_of(m)
    owners = [rec.owner_id] if rec is not None and rec.owner_id else notifications.workspace_admins(workspace_id)
    notifications.notify(workspace_id, owners, "whatsapp_reply", f"WhatsApp reply: {who}", text[:140], record_path(m))
    return True


def member_messages(m: FamilyMember) -> list[WhatsAppMessage]:
    return db.session.query(WhatsAppMessage).filter(WhatsAppMessage.workspace_id == m.workspace_id, WhatsAppMessage.data["family_member_id"].astext == str(m.id)) \
        .order_by(WhatsAppMessage.created_at.desc()).limit(100).all()[::-1]


# ---- the member's own page -----------------------------------------------------------------------------------------

def public_view(m: FamilyMember) -> dict:
    ws = db.session.get(Workspace, m.workspace_id)
    entity, rec = buyer_of(m)
    project = None
    pid = getattr(rec, "project_id", None) if rec is not None else None
    if pid:
        p = db.session.get(Project, pid)
        project = {"name": p.name, "city": p.city, "locality": p.locality, "rera_id": p.rera_id,
                   "possession": p.possession_date.isoformat() if p.possession_date else None} if p else None
    walks = db.session.query(Walkthrough).filter(Walkthrough.member_id == m.id, Walkthrough.status != "cancelled", Walkthrough.starts_at > utcnow() - dt.timedelta(hours=2)) \
        .order_by(Walkthrough.starts_at).all()
    return {
        "workspace": {"name": ws.name, "logo_url": (ws.settings or {}).get("branding", {}).get("logo_url") or ws.logo_url},
        "member": {"first_name": m.name.split(" ")[0], "timezone": m.timezone, "place": place(m.timezone), "currency": m.currency, "is_nri": m.is_nri},
        "project": project, "prices": price_lines(m, ws),
        "checklist": [{k: v for k, v in i.items() if k != "done_at"} for i in checklist_view(m)] if m.is_nri else [],
        "walkthroughs": [{"id": str(w.id), "status": w.status, "starts_at": w.starts_at.isoformat(), "local_label": local_label(w.starts_at, m.timezone),
                          "meeting_url": w.meeting_url if w.status == "confirmed" else None} for w in walks],
    }


def parse_local(value: str, tz: str) -> dt.datetime:
    """'2026-10-20T19:30' in their zone (or an ISO time with an offset) -> aware UTC."""
    try:
        when = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(422, "validation_error", "Pick a date and time", {"starts_at": "Invalid"})
    if when.tzinfo is None:
        when = when.replace(tzinfo=zone(tz))
    return when.astimezone(dt.timezone.utc)


def check_slot(when: dt.datetime) -> None:
    now = utcnow()
    if when < now + dt.timedelta(minutes=30):
        raise ApiError(422, "validation_error", "Pick a time at least 30 minutes from now", {"starts_at": "Too soon"})
    if when > now + dt.timedelta(days=90):
        raise ApiError(422, "validation_error", "Pick a time in the next 3 months", {"starts_at": "Too far"})


def new_walkthrough(m: FamilyMember, when: dt.datetime, *, via: str, note: str | None = None, tz: str | None = None) -> Walkthrough:
    from app.services import notifications

    check_slot(when)
    entity, rec = buyer_of(m)
    w = Walkthrough(workspace_id=m.workspace_id, member_id=m.id, starts_at=when, timezone=tz or m.timezone, status="requested", requested_via=via, note=note,
                    project_id=getattr(rec, "project_id", None), unit_id=getattr(rec, "unit_id", None))
    db.session.add(w)
    db.session.flush()
    ist = when.astimezone(zone("Asia/Kolkata"))
    title = f"{describe(m)} asked for a video walkthrough" if via == "link" else f"Video walkthrough requested for {describe(m)}"
    body = f"{local_label(when, w.timezone)} ({ist:%d %b}, {ist.strftime('%I:%M %p').lstrip('0').lower()} IST)" + (f"\n{note}" if note else "")
    activities.log_activity("meeting", title, workspace_id=m.workspace_id, body=body, data={"walkthrough_id": str(w.id), "family_member_id": str(m.id)}, **links(m))
    if via == "link":
        owners = [rec.owner_id] if rec is not None and rec.owner_id else notifications.workspace_admins(m.workspace_id)
        notifications.notify(m.workspace_id, owners, "meeting_reminder", f"{title}. Confirm it with a meeting link.", body, record_path(m), {"walkthrough_id": str(w.id)})
    return w
