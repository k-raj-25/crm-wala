"""Real-estate inventory: unit statuses, tower generation, holds, and lead⇄unit matching."""
from __future__ import annotations

import datetime as dt
import decimal

from flask import g
from sqlalchemy import func, or_

from app.core.errors import ApiError
from app.extensions import db
from app.models import Contact, Lead, Project, Tower, Unit, UnitEvent, User
from app.models.base import utcnow

# Single source of truth for what each colour on the building means (mirrored in the web app's constants).
STATUSES: dict[str, dict[str, str]] = {
    "vacant": {"label": "Vacant", "hint": "Empty, not listed yet"},
    "for_sale": {"label": "For sale", "hint": "Listed for sale"},
    "for_rent": {"label": "For rent", "hint": "Listed for rent"},
    "on_hold": {"label": "On hold", "hint": "Held for a client"},
    "booked": {"label": "Booked", "hint": "Token paid"},
    "sold": {"label": "Sold", "hint": "Sale completed"},
    "rented": {"label": "Rented", "hint": "Currently on rent"},
    "self_occupied": {"label": "Self occupied", "hint": "Lived in by the owner"},
}
AVAILABLE = ("vacant", "for_sale", "for_rent")  # a client could still take these
DEFAULT_HOLD_HOURS, MAX_HOLD_HOURS = 48, 24 * 30
OPEN_LEAD_STATUSES = ("new", "contacted", "qualified")


def unit_number(floor: int, n: int) -> str:
    """Ground floor → 001, 002 …; floor 3 → 301, 302 …; floor 10 → 1001, 1002 …"""
    return f"{n:03d}" if floor == 0 else f"{floor}{n:02d}"


def floor_label(floor: int) -> str:
    return "Ground Floor" if floor == 0 else f"Floor {floor:02d}"


def add_floor_units(tower: Tower, floor: int, count: int, *, kind="apartment", bhk=None, area=None, sale_price=None, monthly_rent=None, status="vacant") -> list[Unit]:
    now = utcnow()
    out = []
    for i in range(1, count + 1):
        u = Unit(workspace_id=tower.workspace_id, project_id=tower.project_id, tower_id=tower.id, floor=floor, position=i, number=unit_number(floor, i),
                 kind=kind, bhk=bhk, area_sqft=area, sale_price=sale_price, monthly_rent=monthly_rent, status=status, status_changed_at=now)
        db.session.add(u)
        out.append(u)
    return out


def generate_tower(tower: Tower, units_per_floor: int, **defaults) -> int:
    floors = ([0] if tower.has_ground else []) + list(range(1, tower.floors + 1))
    n = 0
    for f in floors:
        n += len(add_floor_units(tower, f, units_per_floor, **defaults))
    db.session.flush()
    return n


# ---- status changes --------------------------------------------------------------------------------------------------

def _fallback_status(u: Unit) -> str:
    return "for_sale" if u.sale_price else "for_rent" if u.monthly_rent else "vacant"


def log_event(unit: Unit, type_: str, *, from_status=None, to_status=None, note=None, lead_id=None, contact_id=None, user_id=None) -> UnitEvent:
    uid = user_id or (g.user.id if getattr(g, "user", None) else None)
    e = UnitEvent(workspace_id=unit.workspace_id, unit_id=unit.id, type=type_, from_status=from_status, to_status=to_status,
                  note=(note or None) and note[:500], user_id=uid, lead_id=lead_id, contact_id=contact_id)
    db.session.add(e)
    return e


def apply_status(unit: Unit, status: str, *, note: str | None = None, lead_id=None, contact_id=None, hold_hours: int | None = None, user_id=None) -> None:
    if status not in STATUSES:
        raise ApiError(422, "validation_error", "Unknown unit status", {"status": "Choose a valid status"})
    before = unit.status
    if status == before and status != "on_hold":
        return
    now = utcnow()
    if status == "on_hold":
        hours = hold_hours or DEFAULT_HOLD_HOURS
        if hours < 1 or hours > MAX_HOLD_HOURS:
            raise ApiError(422, "validation_error", "A hold can last between 1 hour and 30 days", {"hold_hours": "Out of range"})
        unit.hold_until = now + dt.timedelta(hours=hours)
        unit.held_by = user_id or (g.user.id if getattr(g, "user", None) else None)
        unit.hold_lead_id = lead_id
    else:
        unit.hold_until = unit.held_by = None
        unit.hold_lead_id = lead_id if status == "booked" else None
    if status in ("booked", "sold", "rented"):
        if contact_id:
            unit.occupant_contact_id = contact_id
    elif status in ("vacant", "for_sale", "for_rent", "on_hold"):
        unit.occupant_contact_id = None if status != "on_hold" else unit.occupant_contact_id
    unit.status, unit.status_changed_at = status, now
    log_event(unit, "status", from_status=before, to_status=status, note=note, lead_id=lead_id, contact_id=contact_id, user_id=user_id)


def release_expired_holds(workspace_id=None) -> int:
    """Turn lapsed holds back into sellable stock. Runs lazily on reads and from the scheduler."""
    q = db.session.query(Unit).filter(Unit.status == "on_hold", Unit.hold_until.isnot(None), Unit.hold_until < utcnow(), Unit.deleted_at.is_(None))
    if workspace_id:
        q = q.filter(Unit.workspace_id == workspace_id)
    n = 0
    for u in q.all():
        before = u.status
        u.status, u.status_changed_at = _fallback_status(u), utcnow()
        u.hold_until = u.held_by = u.hold_lead_id = None
        log_event(u, "status", from_status=before, to_status=u.status, note="Hold expired", user_id=None)
        n += 1
    if n:
        db.session.flush()
    return n


# ---- stats ----------------------------------------------------------------------------------------------------------

def counts_by(group_col, ids: list) -> dict:
    """{group_id: {status: n}} for the given project/tower ids."""
    out: dict = {i: {} for i in ids}
    if not ids:
        return out
    rows = db.session.query(group_col, Unit.status, func.count()).filter(group_col.in_(ids), Unit.deleted_at.is_(None)).group_by(group_col, Unit.status).all()
    for gid, st, n in rows:
        out[gid][st] = n
    return out


def summarize(counts: dict[str, int]) -> dict:
    total = sum(counts.values())
    avail = sum(counts.get(s, 0) for s in AVAILABLE)
    closed = counts.get("sold", 0) + counts.get("rented", 0)
    return {"counts": counts, "total": total, "available": avail, "closed": closed, "occupancy_pct": round(100 * (total - avail) / total) if total else 0}


# ---- matching -------------------------------------------------------------------------------------------------------

def _num(v) -> float | None:
    return float(v) if v is not None else None


def _sale_ish(u: Unit) -> bool:
    return u.status == "for_sale" or (u.status in ("vacant", "on_hold") and u.sale_price is not None)


def _rent_ish(u: Unit) -> bool:
    return u.status == "for_rent" or (u.status in ("vacant", "on_hold") and u.monthly_rent is not None and u.sale_price is None)


def score_match(lead: Lead, u: Unit) -> tuple[int, list[str]] | None:
    """None = not a fit. Otherwise (score, human reasons)."""
    reasons: list[str] = []
    sale, rent = _sale_ish(u), _rent_ish(u)
    if lead.intent in ("buy", "invest"):
        if not sale:
            return None
        price, lo, hi = _num(u.sale_price), _num(lead.budget_min), _num(lead.budget_max)
    elif lead.intent == "rent":
        if not rent:
            return None
        price, lo, hi = _num(u.monthly_rent), _num(lead.budget_min), _num(lead.budget_max)
    elif lead.intent in (None, ""):
        if not (sale or rent):
            return None
        price, lo, hi = _num(u.sale_price) if sale else _num(u.monthly_rent), _num(lead.budget_min), _num(lead.budget_max)
    else:  # sell / lease: these are owners, not buyers
        return None
    score = 10 + (5 if u.status in ("for_sale", "for_rent") else 0)  # actively listed stock first
    if lead.bhk:
        if (u.bhk or "").lower() != lead.bhk.lower():
            return None
        score += 30
        reasons.append(u.bhk or "")
    if lead.property_type:
        if lead.property_type != u.kind:
            return None
        score += 10
    if hi is not None and price is not None:
        if price > hi * 1.1:
            return None
        score += 30 if price <= hi else 10
        reasons.append("within budget" if price <= hi else "slightly above budget")
    if lo is not None and price is not None and price < lo * 0.7:
        return None
    if lead.project_id and lead.project_id == u.project_id:
        score += 20
        reasons.append("their chosen project")
    return score, [r for r in reasons if r]


def matching_leads(unit: Unit, limit: int = 8) -> list[dict]:
    leads = db.session.query(Lead).filter(Lead.workspace_id == unit.workspace_id, Lead.deleted_at.is_(None), Lead.status.in_(OPEN_LEAD_STATUSES),
                                          or_(Lead.intent.is_(None), Lead.intent.in_(("buy", "invest", "rent")))).limit(500).all()
    scored = []
    for ld in leads:
        m = score_match(ld, unit)
        if m:
            scored.append((m[0], ld, m[1]))
    scored.sort(key=lambda t: (-t[0], t[1].created_at))
    return [{"id": str(ld.id), "name": ld.name, "phone": ld.phone, "intent": ld.intent, "bhk": ld.bhk, "budget_min": _num(ld.budget_min),
             "budget_max": _num(ld.budget_max), "status": ld.status, "score": s, "reasons": r} for s, ld, r in scored[:limit]]


def matching_units(lead: Lead, limit: int = 12) -> list[Unit]:
    q = db.session.query(Unit).filter(Unit.workspace_id == lead.workspace_id, Unit.deleted_at.is_(None), Unit.status.in_(AVAILABLE + ("on_hold",)))
    if lead.project_id:
        q = q.order_by((Unit.project_id == lead.project_id).desc(), Unit.sale_price)
    scored = []
    for u in q.limit(1500).all():
        m = score_match(lead, u)
        if m:
            scored.append((m[0], u, m[1]))
    scored.sort(key=lambda t: -t[0])
    out = []
    for s, u, r in scored[:limit]:
        u._match = {"score": s, "reasons": r}  # type: ignore[attr-defined]
        out.append(u)
    return out


def people(ids: set) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = db.session.query(Contact.id, Contact.first_name, Contact.last_name, Contact.phone).filter(Contact.id.in_(ids)).all()
    return {r.id: {"id": str(r.id), "name": f"{r.first_name} {r.last_name or ''}".strip(), "phone": r.phone} for r in rows}


def user_names(ids: set) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {r.id: r.name for r in db.session.query(User.id, User.name).filter(User.id.in_(ids)).all()}


def money(v) -> float | None:
    return float(v) if isinstance(v, (decimal.Decimal, int, float)) else None



def link_project(data: dict) -> dict:
    """If a record points at a unit but not a project, take the project from the unit."""
    if data.get("unit_id") and not data.get("project_id"):
        data["project_id"] = db.session.query(Unit.project_id).filter(Unit.id == data["unit_id"]).scalar()
    return data


def sync_deal_to_unit(deal, stage_kind: str) -> None:
    """A deal won on a unit closes the unit (sold or rented); a deal lost releases a held/booked unit."""
    if not deal.unit_id or stage_kind not in ("won", "lost"):
        return
    unit = db.session.get(Unit, deal.unit_id)
    if unit is None or unit.deleted_at is not None:
        return
    if stage_kind == "won":
        status = "rented" if (unit.status in ("for_rent", "rented") or (unit.monthly_rent and not unit.sale_price)) else "sold"
        apply_status(unit, status, note=f"Deal won: {deal.name}", contact_id=deal.contact_id)
    elif unit.status in ("on_hold", "booked"):
        apply_status(unit, _fallback_status(unit), note=f"Deal lost: {deal.name}")
