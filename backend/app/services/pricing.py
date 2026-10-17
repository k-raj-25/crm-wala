"""Airline-style pricing: read demand for every flat from what the CRM already sees (holds, site visits, comparisons, enquiries,
matching buyers), suggest price changes for groups of similar flats, and after the owner applies one, track whether sales sped up.

Rule-based on purpose: it works without an AI key, and every suggestion can say exactly why. Nothing changes a price until the owner
applies a suggestion; each applied change is written to the audit log and to every flat's history.
"""
from __future__ import annotations

import datetime as dt
import decimal
import uuid
from dataclasses import dataclass, field

from flask import g
from sqlalchemy import func, or_

from app.core.errors import ApiError
from app.extensions import db
from app.models import Lead, PriceChange, Project, Tower, Unit, UnitEvent
from app.models.base import utcnow
from app.services import audit, inventory
from app.services.comparison import inr

WINDOW_DAYS = 60  # how far back demand is read
COOLDOWN_DAYS = 30  # after a change (or a dismissal) a group is left alone so its effect can be measured
MIN_TRACK_DAYS = 7  # before this, "did it work?" is too early to call
SELLABLE = ("vacant", "for_sale")  # a price change only touches flats nobody has been quoted on yet
TAKEN = ("booked", "sold")
OUT_OF_SCOPE = ("for_rent", "rented", "self_occupied")  # rentals and lived-in flats aren't priced for sale here
RAISE_PCT, RAISE_PCT_HOT, CUT_PCT = decimal.Decimal(3), decimal.Decimal(5), decimal.Decimal(-2)
MAX_PCT = 20

# What each signal is worth when ranking a flat's demand. Matching buyers are weak evidence (they haven't asked for this flat), so on
# their own they can make a flat "cool" but never "warm".
WEIGHTS = {"holds": 3, "visits": 2, "interested": 2, "compared": 1}
MATCHED_WEIGHT, MATCHED_CAP = 0.5, 3


# ---- demand per flat -----------------------------------------------------------------------------------------------

@dataclass
class Demand:
    holds: int = 0
    visits: int = 0
    compared: int = 0
    interested: int = 0  # open enquiries pointing at this exact flat
    matched: int = 0  # open buyers whose need (size, budget) fits it
    taken_recent: int = 0  # booked or sold inside the window
    matched_ids: set = field(default_factory=set)

    @property
    def score(self) -> float:
        return sum(getattr(self, k) * w for k, w in WEIGHTS.items()) + min(self.matched, MATCHED_CAP) * MATCHED_WEIGHT

    def as_dict(self) -> dict:
        return {"holds": self.holds, "visits": self.visits, "compared": self.compared, "interested": self.interested, "matched": self.matched,
                "score": round(self.score, 1)}


def level(score: float) -> str:
    return "hot" if score >= 8 else "warm" if score >= 3 else "cool" if score > 0 else "cold"


def _units(project_id, tower_id=None) -> list[Unit]:
    q = db.session.query(Unit).filter(Unit.project_id == project_id, Unit.deleted_at.is_(None))
    if tower_id:
        q = q.filter(Unit.tower_id == tower_id)
    return q.all()


def demand_for(units: list[Unit], since: dt.datetime | None = None) -> dict[uuid.UUID, Demand]:
    since = since or utcnow() - dt.timedelta(days=WINDOW_DAYS)
    out = {u.id: Demand() for u in units}
    if not units:
        return out
    ids = list(out)
    rows = db.session.query(UnitEvent.unit_id, UnitEvent.type, UnitEvent.to_status, func.count()).filter(
        UnitEvent.unit_id.in_(ids), UnitEvent.created_at >= since,
        or_(UnitEvent.type.in_(("visit", "compared")), (UnitEvent.type == "status") & UnitEvent.to_status.in_(("on_hold",) + TAKEN)),
    ).group_by(UnitEvent.unit_id, UnitEvent.type, UnitEvent.to_status).all()
    for uid, typ, to, n in rows:
        d = out[uid]
        if typ == "visit":
            d.visits += n
        elif typ == "compared":
            d.compared += n
        elif to == "on_hold":
            d.holds += n
        else:
            d.taken_recent += n
    for uid, n in db.session.query(Lead.unit_id, func.count()).filter(Lead.unit_id.in_(ids), Lead.deleted_at.is_(None),
                                                                       Lead.status.in_(inventory.OPEN_LEAD_STATUSES)).group_by(Lead.unit_id).all():
        out[uid].interested += n
    # buyers whose requirement fits: flats with the same size, price and status match the same buyers, so score each shape once
    leads = db.session.query(Lead).filter(Lead.workspace_id == units[0].workspace_id, Lead.deleted_at.is_(None), Lead.status.in_(inventory.OPEN_LEAD_STATUSES),
                                          or_(Lead.intent.is_(None), Lead.intent.in_(("buy", "invest")))).limit(2000).all()
    seen: dict[tuple, set] = {}
    for u in units:
        if u.status not in SELLABLE + ("on_hold",):
            continue
        shape = (u.project_id, u.kind, (u.bhk or "").lower(), u.sale_price, u.monthly_rent, u.status)
        if shape not in seen:
            seen[shape] = {ld.id for ld in leads if inventory.score_match(ld, u)}
        out[u.id].matched_ids = seen[shape]
        out[u.id].matched = len(seen[shape])
    return out


def unit_levels(project_id, tower_id=None) -> dict:
    """{unit_id: {level, score, holds, ...}} for colouring the tower. Flats already booked, sold or rented have no level."""
    units = _units(project_id, tower_id)
    dem = demand_for(units)
    out = {}
    for u in units:
        if u.status in TAKEN or u.status in OUT_OF_SCOPE:
            continue
        d = dem[u.id]
        out[str(u.id)] = {**d.as_dict(), "level": level(d.score)}
    return out


# ---- groups of similar flats -------------------------------------------------------------------------------------

def floor_band(floor: int) -> str:
    """Ground floor alone, then bands of five floors (1-5, 6-10 …): close enough that buyers see them as the same flat."""
    return "g" if floor <= 0 else str((floor - 1) // 5)


def segment_key(u: Unit) -> str:
    return f"{u.tower_id}|{(u.bhk or u.kind).strip()}|{(u.facing or '').strip()}|{floor_band(u.floor)}"


def _plural(bhk: str) -> str:
    b = bhk.replace(" BHK", "BHK")
    return b if b.endswith("s") else b + "s"


def segment_label(units: list[Unit], tower_name: str) -> str:
    u = units[0]
    floors = sorted({x.floor for x in units})
    what = u.bhk or {"apartment": "flat"}.get(u.kind, u.kind)
    what = _plural(what) if len(units) > 1 else what.replace(" BHK", "BHK")
    if u.facing:
        what = f"{u.facing}-facing {what}"
    where = "on the ground floor" if floors == [0] else f"on floor {floors[0]}" if len(floors) == 1 else f"on floors {floors[0]} to {floors[-1]}"
    return f"{what[0].upper()}{what[1:]} {where}, {tower_name}"


@dataclass
class Segment:
    key: str
    label: str
    tower_id: uuid.UUID
    units: list[Unit]
    holds: int = 0
    visits: int = 0
    compared: int = 0
    interested: int = 0
    matched: int = 0
    taken_recent: int = 0

    @property
    def left(self) -> list[Unit]:
        return [u for u in self.units if u.status in SELLABLE and u.sale_price]

    @property
    def listed(self) -> list[Unit]:
        return [u for u in self.left if u.status == "for_sale"]

    def targets(self, rule: str) -> list[Unit]:
        """The flats a change touches: a raise covers every unsold flat; a cut only the ones on the market (not yet listed means no one could ask)."""
        return self.listed if rule == "cut_cold" else self.left

    @property
    def taken(self) -> int:
        return sum(1 for u in self.units if u.status in TAKEN)

    def evidence(self) -> dict:
        return {"flats": len(self.units), "left": len(self.left), "taken": self.taken, "on_hold": sum(1 for u in self.units if u.status == "on_hold"),
                "holds": self.holds, "visits": self.visits, "compared": self.compared, "interested": self.interested, "matched": self.matched,
                "booked_recently": self.taken_recent, "window_days": WINDOW_DAYS}


def segments(project_id) -> list[Segment]:
    units = [u for u in _units(project_id) if u.status not in OUT_OF_SCOPE and (u.sale_price or u.status in TAKEN)]
    towers = dict(db.session.query(Tower.id, Tower.name).filter(Tower.project_id == project_id).all())
    dem = demand_for(units)
    groups: dict[str, list[Unit]] = {}
    for u in units:
        groups.setdefault(segment_key(u), []).append(u)
    out = []
    for key, us in groups.items():
        us.sort(key=lambda x: (x.floor, x.position))
        s = Segment(key=key, label=segment_label(us, towers.get(us[0].tower_id, "Tower")), tower_id=us[0].tower_id, units=us)
        matched: set = set()
        for u in us:
            d = dem[u.id]
            s.holds += d.holds; s.visits += d.visits; s.compared += d.compared; s.interested += d.interested; s.taken_recent += d.taken_recent
            matched |= d.matched_ids
        s.matched = len(matched)
        out.append(s)
    return out


# ---- suggestions -------------------------------------------------------------------------------------------------

def _n(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _left_phrase(n: int) -> str:
    return "only 1 is left" if n == 1 else f"only {n} are left"


def suggest(s: Segment) -> dict | None:
    """One suggestion for a group of flats, or None when its price looks right."""
    left = len(s.left)
    if not left:
        return None
    pull = s.holds + s.taken_recent + s.visits * 0.5 + s.interested * 0.5  # people who reached for these flats
    total = len(s.units)
    if pull >= 3 and pull / left >= 2 and (s.taken + s.holds) / total >= 0.5:
        pct = RAISE_PCT_HOT if pull / left >= 6 and left <= 2 else RAISE_PCT
        signals = [p for p in (
            _n(s.holds, "hold") if s.holds else None, f"{s.taken_recent} booked" if s.taken_recent else None,
            _n(s.visits, "site visit") if s.visits else None) if p]
        why = " and ".join([", ".join(signals[:-1]), signals[-1]] if len(signals) > 1 else signals) if signals else _n(s.interested, "enquiry", "enquiries")
        return {"rule": "raise_hot", "pct": float(pct),
                "headline": f"{s.label} had {why} in {WINDOW_DAYS} days and {_left_phrase(left)}. Raise the price by {pct:g}%."}
    quiet = not (s.holds or s.visits or s.compared or s.interested or s.taken_recent)
    listed = s.listed
    stale = all(u.status_changed_at and u.status_changed_at <= utcnow() - dt.timedelta(days=WINDOW_DAYS) for u in listed)
    if quiet and listed and stale:
        them = "it" if len(listed) == 1 else "them"
        extra = f" {_n(s.matched, 'buyer')} in your leads {'fits' if s.matched == 1 else 'fit'} {them} but none asked." if s.matched else ""
        return {"rule": "cut_cold", "pct": float(CUT_PCT),
                "headline": f"{s.label}: no holds, visits or enquiries in {WINDOW_DAYS} days.{extra} Cut the price by {abs(CUT_PCT):g}%."}
    return None


def _recent_actions(project_id) -> dict[str, PriceChange]:
    since = utcnow() - dt.timedelta(days=COOLDOWN_DAYS)
    rows = db.session.query(PriceChange).filter(PriceChange.project_id == project_id, PriceChange.created_at >= since,
                                                PriceChange.status.in_(("applied", "dismissed"))).all()
    return {r.segment_key: r for r in rows}


def _price_range(units: list[Unit]) -> dict:
    prices = [float(u.sale_price) for u in units if u.sale_price]
    return {"min": min(prices), "max": max(prices)} if prices else {"min": None, "max": None}


def suggestions(project_id) -> list[dict]:
    recent = _recent_actions(project_id)
    out = []
    for s in segments(project_id):
        if s.key in recent:
            continue
        sg = suggest(s)
        if not sg:
            continue
        left = s.targets(sg["rule"])
        out.append({**sg, "id": f"{sg['rule']}:{s.key}", "segment_key": s.key, "segment_label": s.label, "tower_id": str(s.tower_id),
                    "evidence": s.evidence(), "price": _price_range(left),
                    "units": [{"id": str(u.id), "number": u.number, "floor": u.floor, "status": u.status, "price": float(u.sale_price)} for u in left]})
    # biggest opportunity first: raises before cuts, then by how much stock the change touches
    out.sort(key=lambda x: (x["rule"] != "raise_hot", -sum(u["price"] for u in x["units"])))
    return out


# ---- acting on a suggestion --------------------------------------------------------------------------------------

def _segment(project_id, key: str) -> Segment:
    for s in segments(project_id):
        if s.key == key:
            return s
    raise ApiError(404, "not_found", "Those flats are no longer in this project")


def new_price(before: decimal.Decimal, pct: decimal.Decimal) -> decimal.Decimal:
    """Rounded to the nearest ₹1,000, the way price lists are written."""
    return (before * (1 + pct / 100) / 1000).quantize(decimal.Decimal(1), rounding=decimal.ROUND_HALF_UP) * 1000


def _rupees(v) -> str:
    return inr(v)


def apply(project: Project, key: str, rule: str, pct: decimal.Decimal, headline: str | None) -> PriceChange:
    if pct == 0 or abs(pct) > MAX_PCT:
        raise ApiError(422, "validation_error", f"Choose a change between -{MAX_PCT}% and {MAX_PCT}%", {"pct": "Out of range"})
    if key in _recent_actions(project.id) and _recent_actions(project.id)[key].status == "applied":
        raise ApiError(409, "recently_changed", f"These flats were repriced in the last {COOLDOWN_DAYS} days. Give that change time to show its effect, or undo it first.")
    s = _segment(project.id, key)
    left = s.targets(rule)
    if not left:
        raise ApiError(409, "nothing_to_change", "None of these flats is still for sale")
    rows = []
    for u in left:
        before = u.sale_price
        u.sale_price = new_price(before, pct)
        rows.append({"id": str(u.id), "number": u.number, "before": float(before), "after": float(u.sale_price)})
        inventory.log_event(u, "price", note=f"Price {_rupees(before)} → {_rupees(u.sale_price)} ({pct:+g}%), from a pricing suggestion")
    pc = PriceChange(workspace_id=project.workspace_id, project_id=project.id, tower_id=s.tower_id, status="applied", rule=rule, segment_key=key,
                     segment_label=s.label, pct=pct, headline=(headline or "")[:400] or None, evidence=s.evidence(), units=rows, decided_by=g.user.id)
    db.session.add(pc)
    db.session.flush()
    audit.record("pricing.applied", entity_type="project", entity_id=project.id,
                 summary=f"{project.name}: {s.label} repriced {pct:+g}% ({_n(len(rows), 'flat')})"[:400],
                 before={r["number"]: r["before"] for r in rows}, after={r["number"]: r["after"] for r in rows})
    return pc


def dismiss(project: Project, key: str, rule: str, headline: str | None) -> PriceChange:
    s = _segment(project.id, key)
    pc = PriceChange(workspace_id=project.workspace_id, project_id=project.id, tower_id=s.tower_id, status="dismissed", rule=rule, segment_key=key,
                     segment_label=s.label, pct=decimal.Decimal(0), headline=(headline or "")[:400] or None, evidence=s.evidence(), units=[], decided_by=g.user.id)
    db.session.add(pc)
    db.session.flush()
    audit.record("pricing.dismissed", entity_type="project", entity_id=project.id, summary=f"{project.name}: kept the price of {s.label}"[:400])
    return pc


def undo(pc: PriceChange) -> dict:
    """Put back the old prices. A flat whose price someone has changed by hand since is left alone."""
    if pc.status != "applied":
        raise ApiError(409, "not_applied", "Only an applied price change can be undone")
    units = {u.id: u for u in db.session.query(Unit).filter(Unit.id.in_([uuid.UUID(r["id"]) for r in pc.units]), Unit.deleted_at.is_(None)).all()}
    restored, skipped = [], []
    for r in pc.units:
        u = units.get(uuid.UUID(r["id"]))
        if u is None or u.sale_price is None or float(u.sale_price) != r["after"]:
            skipped.append(r["number"])
            continue
        u.sale_price = decimal.Decimal(str(r["before"]))
        restored.append(r["number"])
        inventory.log_event(u, "price", note=f"Price {_rupees(r['after'])} → {_rupees(r['before'])}, price change undone")
    pc.status, pc.undone_at, pc.undone_by = "undone", utcnow(), g.user.id
    audit.record("pricing.undone", entity_type="project", entity_id=pc.project_id,
                 summary=f"Undid the {float(pc.pct):+g}% change on {pc.segment_label} ({_n(len(restored), 'flat')} restored)"[:400],
                 before={r["number"]: r["after"] for r in pc.units if r["number"] in restored}, after={r["number"]: r["before"] for r in pc.units if r["number"] in restored})
    return {"restored": restored, "skipped": skipped}


# ---- did it work? ------------------------------------------------------------------------------------------------

def _pace(unit_ids: list, start: dt.datetime, end: dt.datetime) -> dict:
    rows = db.session.query(UnitEvent.to_status, func.count()).filter(UnitEvent.unit_id.in_(unit_ids), UnitEvent.type == "status",
                                                                     UnitEvent.created_at >= start, UnitEvent.created_at < end,
                                                                     UnitEvent.to_status.in_(("on_hold",) + TAKEN)).group_by(UnitEvent.to_status).all()
    c = dict(rows)
    return {"holds": c.get("on_hold", 0), "booked": c.get("booked", 0) + c.get("sold", 0)}


def tracking(pc: PriceChange) -> dict | None:
    """Same number of days before and after the change, for the same flats: holds and bookings in each, and a plain verdict."""
    if pc.status == "dismissed" or not pc.units:
        return None
    end = pc.undone_at or utcnow()
    days = min((end - pc.created_at).total_seconds() / 86400, WINDOW_DAYS)
    ids = [uuid.UUID(r["id"]) for r in pc.units]
    span = dt.timedelta(days=days)
    before, after = _pace(ids, pc.created_at - span, pc.created_at), _pace(ids, pc.created_at, pc.created_at + span)
    # bookings are what count; holds only decide it when bookings are level
    b, a = (before["booked"], after["booked"]) if before["booked"] != after["booked"] else (before["holds"], after["holds"])
    if days < MIN_TRACK_DAYS:
        verdict = "too_early"
    elif not any(before.values()) and not any(after.values()):
        verdict = "no_interest"
    elif a > b:
        verdict = "faster"
    elif a < b:
        verdict = "slower"
    else:
        verdict = "same"
    return {"days": round(days), "before": before, "after": after, "verdict": verdict}


def changes(project_id, limit: int = 50) -> list[dict]:
    rows = db.session.query(PriceChange).filter(PriceChange.project_id == project_id).order_by(PriceChange.created_at.desc()).limit(limit).all()
    names = inventory.user_names({r.decided_by for r in rows} | {r.undone_by for r in rows})
    return [{**r.to_dict(), "pct": float(r.pct), "decided_by_name": names.get(r.decided_by), "undone_by_name": names.get(r.undone_by), "tracking": tracking(r)} for r in rows]
