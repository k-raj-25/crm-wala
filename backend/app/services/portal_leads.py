"""Leads from property portals (99acres). Each enquiry lands as a lead in "Awaiting review" until an owner accepts it.

99acres has no public pull API. It delivers enquiries two ways, and both end up in `intake()`:
- e-mail: the "You have received a response" mail, forwarded by an inbound-parse provider (SendGrid/Postmark/Mailgun/Zapier)
- lead push: JSON or form fields POSTed to our endpoint, set up by the 99acres account manager

Neither format is formally documented, so parsing is label-based and tolerant: unknown fields are kept in `custom.portal_raw`.
"""
from __future__ import annotations

import decimal
import logging
import re
from dataclasses import dataclass, field

from flask import g
from sqlalchemy import func

from app.extensions import db
from app.models import Lead, Project, Workspace
from app.services import activities, analytics, audit, events, notifications

log = logging.getLogger("app.portal_leads")
PENDING_STATUS = {"key": "pending_review", "label": "Awaiting review", "color": "#f59e0b"}
SOURCE = "99acres"

# label (lower-case, punctuation stripped) -> field. Used for both e-mail "Label: value" lines and push payload keys.
_ALIASES = {
    "name": ("name", "full name", "buyer name", "sender name", "contact name", "responder name", "customer name", "client name", "user name"),
    "email": ("email", "email id", "e mail", "email address", "sender email", "buyer email", "user email"),
    "phone": ("mobile", "phone", "mobile number", "mobile no", "phone number", "phone no", "contact number", "contact no", "sender mobile",
              "buyer mobile", "user mobile", "isd mobile"),
    "message": ("message", "query", "enquiry", "inquiry", "requirement", "comments", "remarks", "query details"),
    "property": ("property", "property details", "project", "project name", "listing", "listing title", "interested in", "regarding",
                 "property name", "property title"),
    "property_id": ("property id", "listing id", "prop id", "property code", "project id"),
    "enquiry_id": ("enquiry id", "inquiry id", "query id", "lead id", "response id", "id"),
    "location": ("city", "location", "locality", "property location"),
    "budget": ("budget", "price", "expected price"),
}
_FIELD_BY_LABEL = {label: f for f, labels in _ALIASES.items() for label in labels}


@dataclass
class Enquiry:
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    message: str | None = None
    property: str | None = None
    property_id: str | None = None
    enquiry_id: str | None = None
    location: str | None = None
    budget: str | None = None
    raw: dict = field(default_factory=dict)


def _label(s: str) -> str:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)  # SenderMobile -> Sender Mobile
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def _clean(v) -> str | None:
    v = re.sub(r"\s+", " ", str(v)).strip(" :-\t") if v is not None else ""
    return v or None


def _assign(e: Enquiry, label: str, value) -> bool:
    f = _FIELD_BY_LABEL.get(_label(label))
    v = _clean(value)
    if not f or not v:
        return False
    if getattr(e, f) is None:
        setattr(e, f, v)
    return True


# ---- parsing ------------------------------------------------------------------------------------------------------------

def looks_like_99acres(from_address: str, subject: str, text: str) -> bool:
    return from_address.lower().endswith(("@99acres.com", ".99acres.com")) or "99acres" in (subject or "").lower()


def parse_email(subject: str, text: str) -> Enquiry:
    """Pull an enquiry out of a 99acres response mail. Handles "Label: value" lines and HTML tables flattened to "Label\\nvalue"."""
    e = Enquiry(raw={"subject": subject})
    lines = [ln.strip() for ln in (text or "").splitlines()]
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r"^([A-Za-z][A-Za-z .\-/]{0,30}?)\s*[:\-–]\s*(.*)$", ln)
        if m and _label(m.group(1)) in _FIELD_BY_LABEL:
            value = m.group(2)
            if not value and i + 1 < len(lines):  # "Name:" with the value on the next line
                value, i = lines[i + 1], i + 1
            _assign(e, m.group(1), value)
        elif _label(ln) in _FIELD_BY_LABEL and i + 1 < len(lines) and lines[i + 1] and _label(lines[i + 1]) not in _FIELD_BY_LABEL:
            _assign(e, ln, lines[i + 1])  # table cell layout
            i += 1
        i += 1
    if e.email is None:
        m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text or "")
        if m and not m.group(0).lower().endswith("99acres.com"):
            e.email = m.group(0)
    if e.phone is None:
        m = re.search(r"(?:\+?91[\s-]*)?[6-9]\d{4}[\s-]?\d{5}\b", text or "")
        e.phone = m.group(0) if m else None
    if e.property is None:
        m = re.search(r"(?:response|enquiry|inquiry|interest)\s+(?:on|for)\s+(?:your\s+)?(?:property|project|listing)?[:\s]*(.+)", subject or "", re.I)
        e.property = _clean(m.group(1)) if m else None
    if e.property_id is None:
        m = re.search(r"\(\s*(?:ID|Property ID)\s*[:#]?\s*([A-Z0-9-]{5,})\s*\)", f"{subject}\n{text}", re.I)
        e.property_id = m.group(1) if m else None
    return e


def parse_push(payload: dict) -> Enquiry:
    """A lead-push record. Field names vary by account set-up, so keys are matched by alias; nested dicts are flattened."""
    e = Enquiry(raw=payload)
    flat: dict = {}

    def walk(d, prefix=""):
        for k, v in d.items():
            if isinstance(v, dict):
                walk(v, f"{prefix}{k} ")
            elif not isinstance(v, list):
                flat.setdefault(f"{prefix}{k}", v)  # nested keys keep their parent: property.id -> "property id", not "id"

    walk(payload)
    for k, v in flat.items():
        _assign(e, k.replace("_", " "), v)
    return e


# ---- mapping onto a lead -----------------------------------------------------------------------------------------------

_CRORE, _LAKH = decimal.Decimal(10_000_000), decimal.Decimal(100_000)


def parse_amount(s: str | None) -> tuple[decimal.Decimal | None, decimal.Decimal | None]:
    """'₹ 1.25 Cr' -> (None, 12500000); '50 Lac - 1 Cr' -> (5000000, 10000000); '85,00,000' -> (None, 8500000)."""
    if not s:
        return None, None
    amounts = []
    for num, unit in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lac|l|k|thousand)?\b", s, re.I):
        n = decimal.Decimal(num.replace(",", ""))
        u = (unit or "").lower()
        n *= _CRORE if u.startswith("cr") else _LAKH if u.startswith("la") or u == "l" else decimal.Decimal(1000) if u in ("k", "thousand") else 1
        amounts.append(n.quantize(decimal.Decimal("1")))
    if not amounts:
        return None, None
    if len(amounts) == 1:
        return None, amounts[0]
    return min(amounts[:2]), max(amounts[:2])


def _requirement(text: str) -> dict:
    t = text.lower()
    out: dict = {}
    if m := re.search(r"(\d+(?:\.5)?)\s*bhk", t):
        out["bhk"] = f"{m.group(1)} BHK"
    for words, kind in ((("apartment", "flat", "bhk", "penthouse", "studio"), "apartment"), (("villa", "independent house", "bungalow", "kothi", "builder floor"), "villa"),
                        (("plot", "land"), "plot"), (("office",), "office"), (("shop", "showroom", "retail"), "shop")):
        if any(w in t for w in words):
            out["property_type"] = kind
            break
    if re.search(r"\b(for rent|on rent|rental|to rent|lease)\b", t):
        out["intent"] = "rent"
    elif re.search(r"\b(for sale|to buy|buy|purchase|resale)\b", t):
        out["intent"] = "buy"
    return out


def _split_name(name: str | None) -> tuple[str, str | None]:
    parts = (name or "").split()
    if not parts:
        return "99acres enquiry", None
    return parts[0][:100], (" ".join(parts[1:])[:100] or None)


def _phone(p: str | None) -> str | None:
    if not p:
        return None
    digits = re.sub(r"[^\d+]", "", p)
    return digits[:40] or None


def _match_project(workspace_id, text: str):
    if not text:
        return None
    t = text.lower()
    for pid, name in db.session.query(Project.id, Project.name).filter(Project.workspace_id == workspace_id, Project.deleted_at.is_(None)):
        if name and name.lower() in t:
            return pid
    return None


def _flag_repeat(lead: Lead) -> None:
    """The same buyer often enquires on several portals; point the reviewer at the existing lead instead of a silent duplicate."""
    digits = re.sub(r"\D", "", lead.phone or "")[-10:]
    conds = []
    if len(digits) == 10:
        conds.append(func.regexp_replace(func.coalesce(Lead.phone, ""), r"\D", "", "g").like(f"%{digits}"))
    if lead.email:
        conds.append(func.lower(Lead.email) == lead.email.lower())
    if not conds:
        return
    from sqlalchemy import or_

    other = db.session.query(Lead).filter(Lead.workspace_id == lead.workspace_id, Lead.id != lead.id, Lead.deleted_at.is_(None), or_(*conds)).order_by(Lead.created_at).first()
    if other is not None:
        lead.tags = sorted(set(lead.tags or []) | {"repeat enquiry"})
        lead.custom = {**(lead.custom or {}), "possible_duplicate_of": str(other.id), "possible_duplicate_source": other.source}


def ensure_pending_status(ws: Workspace) -> None:
    """Workspaces created before this status existed (or that edited their statuses) get it added after "new"."""
    statuses = list((ws.settings or {}).get("lead_statuses") or [])
    if any(s.get("key") == PENDING_STATUS["key"] for s in statuses):
        return
    at = next((i + 1 for i, s in enumerate(statuses) if s.get("key") == "new"), 0)
    statuses.insert(at, dict(PENDING_STATUS))
    ws.settings = {**(ws.settings or {}), "lead_statuses": statuses}


def _existing(ws_id, key: str | None):
    if not key:
        return None
    return db.session.query(Lead).filter(Lead.workspace_id == ws_id, Lead.source == SOURCE, Lead.custom["intake_key"].astext == key).first()


def intake(ws: Workspace, e: Enquiry, *, via: str, dedupe_key: str | None = None) -> tuple[Lead | None, bool]:
    """Create a pending-review lead from a parsed enquiry. Returns (lead, created); (None, False) if there is nobody to contact."""
    if not (e.phone or e.email):
        return None, False
    key = e.enquiry_id or dedupe_key
    if key:
        key = f"{via}:{key}"
        if (found := _existing(ws.id, key)) is not None:
            return found, False
    ensure_pending_status(ws)
    first, last = _split_name(e.name)
    lo, hi = parse_amount(e.budget)
    req = _requirement(" ".join(filter(None, [e.property, e.message, e.raw.get("subject") if isinstance(e.raw.get("subject"), str) else None])))
    desc = "\n".join(filter(None, [e.message, f"Property: {e.property}" if e.property else None, f"Property ID: {e.property_id}" if e.property_id else None]))
    lead = Lead(workspace_id=ws.id, first_name=first, last_name=last, email=(e.email or "").lower()[:254] or None, phone=_phone(e.phone), source=SOURCE,
                status=PENDING_STATUS["key"], owner_id=None, tags=["99acres"], location=(e.location or "")[:160] or None, description=desc or None,
                budget_min=lo, budget_max=hi, project_id=_match_project(ws.id, f"{e.property or ''} {e.message or ''}"), **req,
                custom={"intake_key": key, "portal": SOURCE, "portal_via": via, "portal_property": e.property, "portal_property_id": e.property_id,
                        "portal_enquiry_id": e.enquiry_id, "portal_raw": e.raw})
    db.session.add(lead)
    db.session.flush()
    try:  # read the free-text requirement, tag brokers / spam and repeat buyers; never blocks the enquiry
        from app.services.ai import features

        with db.session.begin_nested():
            features.portal_cleanup(lead)
            _flag_repeat(lead)
    except Exception:
        log.exception("portal lead clean-up failed")
    from app.api.v1.leads import rescore

    rescore(lead)
    activities.log_activity("created", "Enquiry received from 99acres", workspace_id=ws.id, lead_id=lead.id, body=e.message, user_id=None,
                            data={"source": SOURCE, "via": via})
    audit.record("lead.created", entity_type="lead", entity_id=lead.id, workspace_id=ws.id, actor_type="system", actor_label="99acres",
                 summary=f"Lead “{lead.name}” received from 99acres, awaiting review")
    analytics.track("lead_created", {"via": f"99acres_{via}"}, workspace_id=ws.id)
    notifications.notify(ws.id, notifications.workspace_admins(ws.id), "new_lead", f"New 99acres enquiry to review: {lead.name}",
                         (e.property or e.message or "")[:140] or None, f"/app/leads/{lead.id}")
    events.emit("lead.created", {"lead_id": str(lead.id), "name": lead.name, "email": lead.email, "status": lead.status, "source": SOURCE}, workspace_id=ws.id)
    return lead, True


def bind(ws: Workspace) -> None:
    """Request globals the services above expect, for unauthenticated (webhook) requests."""
    g.workspace, g.user, g.permissions, g.features, g.member = ws, None, set(), set(), None
