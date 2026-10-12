"""Deterministic parsers for how Indian property enquiries are actually written.

They do three jobs: power the no-key ("basic") mode, give the model a checked first guess to improve on, and clean data
(imports, phone numbers, "85 lakh" budgets) without spending AI calls. Nothing here talks to a provider.
"""
from __future__ import annotations

import datetime as dt
import re

CRORE, LAKH = 10_000_000, 100_000
_NUM = r"(\d+(?:[.,]\d+)*)"
_UNIT = r"(crores?|cr\.?|c\b|lakhs?|lacs?|lac|l\b|lk\b|k\b|thousand)"
_MONEY = re.compile(rf"(?:₹|rs\.?|inr)?\s*{_NUM}\s*{_UNIT}?", re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?([6-9]\d{2}[\s-]?\d{3}[\s-]?\d{4}|[6-9]\d{4}[\s-]?\d{5})(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_BHK = re.compile(r"(\d(?:\.5)?)\s*-?\s*(?:bhk|bed(?:room)?s?\b|br\b)", re.I)
_WA_LINE = re.compile(r"^\[?\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?\]?\s*(?:-\s*)?([^:]{2,40}):\s*(.*)$", re.I)


def to_number(num: str, unit: str | None) -> float | None:
    try:
        v = float(num.replace(",", ""))
    except ValueError:
        return None
    u = (unit or "").lower().rstrip(".")
    if u.startswith(("cr", "c")):
        return v * CRORE
    if u.startswith(("lakh", "lac", "l")):
        return v * LAKH
    if u in ("k", "thousand"):
        return v * 1000
    return v


def money_values(text: str) -> list[float]:
    """Every amount in the text that is plausibly money (has a unit, a ₹ sign, or is at least 10,000)."""
    out = []
    text = _EMAIL.sub(" ", _PHONE.sub(" ", text or ""))  # a mobile number is not a budget
    for m in _MONEY.finditer(text):
        raw = m.group(0)
        v = to_number(m.group(1), m.group(2))
        if v is None:
            continue
        has_marker = bool(m.group(2)) or re.match(r"\s*(₹|rs|inr)", raw, re.I)
        if has_marker or v >= 10_000:
            out.append(v)
    return out


def parse_budget(text: str) -> tuple[float | None, float | None]:
    """'80L - 1.2 Cr' -> (8e6, 1.2e7); 'under 1.5 cr' -> (None, 1.5e7); 'above 2cr' -> (2e7, None)."""
    if not text:
        return None, None
    t = _EMAIL.sub(" ", _PHONE.sub(" ", text)).lower()
    # Number without a unit followed by a range to a number with one: "80 to 90 lakh"
    m = re.search(rf"{_NUM}\s*(?:-|–|to)\s*{_NUM}\s*{_UNIT}", t)
    if m:
        lo, hi = to_number(m.group(1), m.group(3)), to_number(m.group(2), m.group(3))
        if lo and hi and lo <= hi:
            return lo, hi
    vals = money_values(t)
    if not vals:
        return None, None
    if len(vals) >= 2:
        lo, hi = sorted(vals[:2])
        return lo, hi
    v = vals[0]
    if re.search(r"(above|more than|minimum|min\.?|at least|starting|from)\s*(?:₹|rs\.?)?\s*\d", t):
        return v, None
    return None, v


def normalize_phone(raw: str | None) -> str | None:
    """Indian mobiles -> '+91 98765 43210'. Anything else is returned trimmed (we don't guess foreign formats)."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return f"+91 {digits[:5]} {digits[5:]}"
    return raw.strip() or None


def phones(text: str) -> list[str]:
    return list(dict.fromkeys(normalize_phone(m.group(0)) for m in _PHONE.finditer(text or "")))


def bhk(text: str) -> str | None:
    t = text or ""
    if re.search(r"\bstudio\b|\b1\s*rk\b", t, re.I):
        return "Studio"
    if re.search(r"penthouse", t, re.I):
        return "Penthouse"
    m = _BHK.search(t)
    return f"{m.group(1)} BHK" if m else None


def intent(text: str) -> str | None:
    t = (text or "").lower()
    if re.search(r"\b(rent|rental|on lease|tenant|kiraye|kiraya|pg)\b", t):
        return "rent"
    if re.search(r"\b(lease out|give on rent|let out)\b", t):
        return "lease"
    if re.search(r"\b(sell|selling|resale of my|want to sell|bechna)\b", t):
        return "sell"
    if re.search(r"\b(invest|investment|roi|rental yield)\b", t):
        return "invest"
    if re.search(r"\b(buy|purchase|looking for|need a|want a|wants?|needs?|kharidna|lena)\b", t):
        return "buy"
    return None


def property_type(text: str) -> str | None:
    t = (text or "").lower()
    for pat, v in ((r"\bvilla|independent house|bungalow|row house", "villa"), (r"\bplot|land\b", "plot"), (r"\boffice", "office"),
                   (r"\bshop|showroom|retail", "shop"), (r"\bflat|apartment|bhk|studio|penthouse", "apartment")):
        if re.search(pat, t):
            return v
    return None


def location(text: str) -> str | None:
    m = re.search(r"\b((?i:sector)[\s-]*\d+[a-zA-Z]?\b(?:,?\s*(?!(?:Under|Above|Below|Budget|For|With|And|Near|To)\b)[A-Z][a-z]+)?)", text or "")
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip().title().replace("Sector-", "Sector ")
    m = re.search(r"\b(?:in|at|near|around)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})", text or "")
    if m and m.group(1).lower() not in ("the", "my", "our", "a", "budget"):
        return m.group(1).strip()
    return None


_NOT_NAMES = {"hi", "hello", "dear", "sir", "madam", "team", "regards", "thanks", "budget", "looking", "need", "want", "i", "we", "my", "name"}


def name(text: str) -> tuple[str | None, str | None]:
    t = text or ""
    pats = (r"(?:my name is|name\s*[:\-]|this is|i am|i'm|naam)\s+([A-Za-z][A-Za-z.]+(?:\s+[A-Za-z][A-Za-z.]+){0,2})",
            r"(?:regards|thanks|thank you),?\s*\n\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})")
    for p in pats:
        m = re.search(p, t, re.I)
        if m:
            parts = [w for w in m.group(1).split() if w.lower() not in _NOT_NAMES]
            stop = next((i for i, w in enumerate(parts) if w.lower() in ("and", "from", "looking", "here", "want", "need", "interested")), len(parts))
            parts = parts[:stop]
            if parts:
                return parts[0].title(), " ".join(parts[1:]).title() or None
    m = re.match(r"\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})(?=[\s,:-]+(?:\+?\d|wants?\b|needs?\b|is looking|looking\b|ji\b))", t)
    if m and m.group(1).split()[0].lower() not in _NOT_NAMES:
        first, *rest = m.group(1).split()
        return first, " ".join(rest) or None
    for line in t.splitlines()[:3]:
        line = line.strip()
        if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}", line) and line.split()[0].lower() not in _NOT_NAMES:
            first, *rest = line.split()
            return first, " ".join(rest) or None
    return None, None


def whatsapp_messages(text: str) -> list[dict]:
    """Parse an exported/pasted WhatsApp chat into [{sender, text}]. Lines that don't start a message continue the last one."""
    out: list[dict] = []
    for line in (text or "").splitlines():
        m = _WA_LINE.match(line.strip())
        if m:
            out.append({"sender": m.group(1).strip(), "text": m.group(2).strip()})
        elif out and line.strip():
            out[-1]["text"] += "\n" + line.strip()
    return out


def follow_up_hint(text: str, now: dt.datetime) -> dt.datetime | None:
    """'call me Sunday', 'tomorrow', 'next week', 'in 3 days' -> a 11:00 local-ish follow-up time (UTC-naive callers convert)."""
    t = (text or "").lower()
    base = now.replace(hour=5, minute=30, second=0, microsecond=0)  # 11:00 IST
    if "day after tomorrow" in t or "parso" in t:
        return base + dt.timedelta(days=2)
    if re.search(r"\btomorrow|\bkal\b", t):
        return base + dt.timedelta(days=1)
    m = re.search(r"\bin (\d{1,2}) days?", t)
    if m:
        return base + dt.timedelta(days=int(m.group(1)))
    if "next week" in t:
        return base + dt.timedelta(days=7)
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, d in enumerate(days):
        if re.search(rf"\b{d}\b", t):
            ahead = (i - now.weekday()) % 7 or 7
            return base + dt.timedelta(days=ahead)
    return None


HOT_WORDS = re.compile(r"\b(token|booking amount|book (?:it|now|today)|ready to (?:book|buy|pay)|final(?:ise|ize)|cheque|advance|site visit today|loan (?:approved|sanctioned))\b", re.I)


def lead_from_text(text: str) -> dict:
    """Best-effort lead fields from free text. Only keys we actually found are returned."""
    t = text or ""
    first, last = name(t)
    msgs = whatsapp_messages(t)
    if msgs and not first:
        sender = next((m["sender"] for m in msgs if not re.search(r"\d{5}", m["sender"])), None)
        if sender:
            first, *rest = sender.split()
            last = " ".join(rest) or None
    lo, hi = parse_budget(t)
    ph = phones(t)
    em = _EMAIL.search(t)
    out = {
        "first_name": first, "last_name": last, "phone": ph[0] if ph else None, "email": em.group(0).lower() if em else None,
        "intent": intent(t), "property_type": property_type(t), "bhk": bhk(t), "budget_min": lo, "budget_max": hi, "location": location(t),
    }
    return {k: v for k, v in out.items() if v not in (None, "")}
