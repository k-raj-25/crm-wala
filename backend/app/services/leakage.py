"""Lead leakage radar: signs that leads are quietly leaving the business with a rep.

Hiding phone numbers stops copying; the radar looks for what's left and tells the owner:

1. Lost leads that came back: a lead a rep marked "lost" or "not interested" turns up again as a new lead or client
   (same phone or email), often through a broker or as a walk-in.
2. Phone reveals far above the team: a member who reveals many more client numbers than their teammates (from the
   `phone.revealed` audit rows), and how many of those clients weren't even theirs.
3. Leads that go cold after site visits: a rep whose visited leads get no follow-up (or get marked lost) within
   two weeks of the visit much more often than their teammates' visited leads.

Everything is computed from data the CRM already has (activities, the audit log, duplicate matching by phone), so it
needs no new tables. The owner sees it on the Radar page and gets a weekly summary.
"""
from __future__ import annotations

import datetime as dt
import statistics
from typing import Any

from sqlalchemy import or_

from app.core.crud import users_map
from app.core.permissions import has_permission
from app.extensions import db
from app.models import Activity, AuditLog, Contact, Lead, Meeting, Role, WorkspaceMember
from app.models.base import utcnow

LOST = ("lost", "unqualified")
# Sources a lead usually takes when it's walked out of the door and brought back for a commission.
BACKDOOR_SOURCES = {"broker", "walk_in", "referral", "channel_partner", "site_visit"}
COLD_DAYS = 14  # a visited lead with no follow-up for this long has gone cold
VISIT_WINDOW_MIN = 30  # site-visit rates need a few weeks of visits to mean anything
# Activities that don't count as someone working the lead.
NOT_A_TOUCH = {"created", "updated", "assigned", "system", "file"}

# Thresholds for flagging a rep. Kept loose on purpose: the radar points at something to look at, it doesn't accuse.
REVEAL_MIN = 5  # at least this many reveals in the period
REVEAL_FACTOR = 2  # and at least this many times the team's usual count
VISIT_MIN = 3  # at least this many matured visits
VISIT_RATE_MIN = 0.5  # half or more of them went cold
VISIT_GAP = 0.25  # and at least 25 points above the rest of the team


def _digits(p: str | None) -> str:
    d = "".join(c for c in (p or "") if c.isdigit())
    return d[-10:] if len(d) >= 7 else ""


def _keys(o) -> list[tuple[str, str]]:
    out = []
    if _digits(o.phone):
        out.append(("phone", _digits(o.phone)))
    if o.email:
        out.append(("email", o.email.strip().lower()))
    return out


def _iso(v: dt.datetime | None) -> str | None:
    return v.isoformat() if v else None


def _person(users: dict, uid) -> dict | None:
    u = users.get(uid)
    return {"id": u["id"], "name": u["name"], "avatar_url": u["avatar_url"]} if u else None


# ---- 1. lost leads that came back ----------------------------------------------------------

def lost_leads_back(ws, start: dt.datetime, end: dt.datetime) -> list[dict]:
    """New leads/clients created in the period whose phone or email matches a lead that was marked lost before."""
    newcomers: list[tuple[str, Any]] = []
    for model, kind in ((Lead, "lead"), (Contact, "contact")):
        rows = db.session.query(model).filter(model.workspace_id == ws, model.deleted_at.is_(None), model.created_at >= start, model.created_at <= end,
                                              or_(model.phone.isnot(None), model.email.isnot(None))).limit(5000).all()
        newcomers += [(kind, o) for o in rows]
    if not newcomers:
        return []
    wanted: dict[tuple[str, str], list] = {}
    for kind, o in newcomers:
        for k in _keys(o):
            wanted.setdefault(k, []).append((kind, o))

    lost = db.session.query(Lead).filter(Lead.workspace_id == ws, Lead.deleted_at.is_(None), Lead.status.in_(LOST), Lead.created_at < end,
                                         or_(Lead.phone.isnot(None), Lead.email.isnot(None))).limit(20000).all()
    lost = [o for o in lost if any(k in wanted for k in _keys(o))]
    if not lost:
        return []

    # Who marked it lost, and when: the latest status change into a lost status (else the owner and last update).
    marked: dict = {}
    acts = db.session.query(Activity).filter(Activity.workspace_id == ws, Activity.type == "status_changed", Activity.lead_id.in_([o.id for o in lost])).order_by(Activity.occurred_at).all()
    for a in acts:
        if (a.data or {}).get("to") in LOST:
            marked[a.lead_id] = (a.user_id, a.occurred_at)

    new_lead_ids = {o.id for kind, o in newcomers if kind == "lead"}
    found, seen = [], set()
    for o in lost:
        by, at = marked.get(o.id, (o.owner_id, o.updated_at))
        for key in _keys(o):
            for kind, n in wanted.get(key, []):
                if n.id == o.id or (kind == "contact" and n.source_lead_id in (o.id, *new_lead_ids)) or n.created_at <= at or (o.id, n.id) in seen:
                    continue
                seen.add((o.id, n.id))
                source = getattr(n, "source", None)
                found.append({
                    "lost": {"id": str(o.id), "name": o.name, "status": o.status, "lost_reason": o.lost_reason, "marked_at": _iso(at), "marked_by_id": by,
                             "owner_id": o.owner_id},
                    "back": {"type": kind, "id": str(n.id), "name": n.name, "source": source, "created_at": _iso(n.created_at), "owner_id": n.owner_id},
                    "matched_on": key[0], "gap_days": max(0, (n.created_at - at).days), "backdoor": (source or "") in BACKDOOR_SOURCES,
                })
    users = users_map({x["lost"]["marked_by_id"] for x in found} | {x["lost"]["owner_id"] for x in found} | {x["back"]["owner_id"] for x in found})
    for x in found:
        x["lost"]["marked_by"] = _person(users, x["lost"].pop("marked_by_id"))
        x["lost"]["owner"] = _person(users, x["lost"].pop("owner_id"))
        x["back"]["owner"] = _person(users, x["back"].pop("owner_id"))
    found.sort(key=lambda x: x["back"]["created_at"], reverse=True)
    found.sort(key=lambda x: not x["backdoor"])  # stable: broker / walk-in returns first, newest first within each
    return found


# ---- 2. phone reveals far above the team ---------------------------------------------------

def _revealers(ws) -> set:
    """Active members whose role reveals numbers one at a time (those who see every number never need to)."""
    rows = db.session.query(WorkspaceMember.user_id, Role.permissions).join(Role, Role.id == WorkspaceMember.role_id).filter(
        WorkspaceMember.workspace_id == ws, WorkspaceMember.status == "active").all()
    return {uid for uid, perms in rows if has_permission(perms or [], "phones.reveal") and not has_permission(perms or [], "phones.view")}


def reveal_outliers(ws, start: dt.datetime, end: dt.datetime) -> list[dict]:
    rows = db.session.query(AuditLog.actor_id, AuditLog.entity_type, AuditLog.entity_id).filter(
        AuditLog.workspace_id == ws, AuditLog.action == "phone.revealed", AuditLog.created_at >= start, AuditLog.created_at <= end,
        AuditLog.actor_id.isnot(None)).all()
    team = _revealers(ws) | {r.actor_id for r in rows}
    if not team:
        return []
    owners: dict[str, Any] = {}
    for model, et in ((Lead, "lead"), (Contact, "contact")):
        ids = {r.entity_id for r in rows if r.entity_type == et}
        if ids:
            owners.update({str(i): o for i, o in db.session.query(model.id, model.owner_id).filter(model.id.in_(ids))})
    stats = {uid: {"reveals": 0, "clients": set(), "not_theirs": set()} for uid in team}
    for r in rows:
        s = stats[r.actor_id]
        s["reveals"] += 1
        s["clients"].add(r.entity_id)
        if r.entity_id in owners and owners[r.entity_id] != r.actor_id:
            s["not_theirs"].add(r.entity_id)
    users = users_map(team)
    out = []
    for uid, s in stats.items():
        others = [o["reveals"] for k, o in stats.items() if k != uid]
        usual = statistics.median(others) if others else None
        flagged = bool(others) and s["reveals"] >= REVEAL_MIN and s["reveals"] >= REVEAL_FACTOR * max(usual or 0, 1)
        out.append({"user": _person(users, uid), "reveals": s["reveals"], "clients": len(s["clients"]), "not_their_clients": len(s["not_theirs"]),
                    "team_usual": usual, "times_usual": round(s["reveals"] / usual, 1) if usual else None, "flagged": flagged})
    out = [o for o in out if o["user"]]
    out.sort(key=lambda o: (not o["flagged"], -o["reveals"]))
    return out


# ---- 3. leads that go cold after site visits -----------------------------------------------

def cold_after_visits(ws, now: dt.datetime, days: int) -> list[dict]:
    """Per rep: of their site visits that ended between `days`+14 and 14 days ago, how many saw no follow-up (or a
    "lost") within 14 days, against the rest of the team."""
    hi = now - dt.timedelta(days=COLD_DAYS)
    lo = hi - dt.timedelta(days=days)
    visits = db.session.query(Meeting).filter(Meeting.workspace_id == ws, Meeting.deleted_at.is_(None), Meeting.kind == "site_visit", Meeting.status != "canceled",
                                              Meeting.ends_at >= lo, Meeting.ends_at <= hi, Meeting.organizer_id.isnot(None),
                                              or_(Meeting.lead_id.isnot(None), Meeting.contact_id.isnot(None))).all()
    if not visits:
        return []
    lead_ids = {v.lead_id for v in visits if v.lead_id}
    contact_ids = {v.contact_id for v in visits if v.contact_id}
    conds = []
    if lead_ids:
        conds.append(Activity.lead_id.in_(lead_ids))
    if contact_ids:
        conds.append(Activity.contact_id.in_(contact_ids))
    acts = db.session.query(Activity).filter(Activity.workspace_id == ws, or_(*conds), Activity.occurred_at > lo,
                                             Activity.occurred_at <= now, Activity.type.notin_(NOT_A_TOUCH)).all()
    names = {}
    if lead_ids:
        names.update({i: (f"{f} {l or ''}".strip(), "lead") for i, f, l in db.session.query(Lead.id, Lead.first_name, Lead.last_name).filter(Lead.id.in_(lead_ids))})
    if contact_ids:
        names.update({i: (f"{f} {l or ''}".strip(), "contact") for i, f, l in db.session.query(Contact.id, Contact.first_name, Contact.last_name).filter(Contact.id.in_(contact_ids))})

    per: dict = {}
    for v in visits:
        until = v.ends_at + dt.timedelta(days=COLD_DAYS)
        touched, lost_at = False, None
        for a in acts:
            if not ((v.lead_id and a.lead_id == v.lead_id) or (v.contact_id and a.contact_id == v.contact_id)):
                continue
            if not (v.ends_at < a.occurred_at <= until) or (a.data or {}).get("meeting_id") == str(v.id):
                continue
            if a.type == "status_changed" and (a.data or {}).get("to") in LOST:
                lost_at = lost_at or a.occurred_at
            else:
                touched = True
        cold = lost_at is not None or not touched
        p = per.setdefault(v.organizer_id, {"visits": 0, "cold": 0, "examples": []})
        p["visits"] += 1
        if cold:
            p["cold"] += 1
            ident = v.lead_id or v.contact_id
            name, kind = names.get(ident, ("Unknown", "lead"))
            p["examples"].append({"visit_id": str(v.id), "title": v.title, "visited_at": _iso(v.starts_at), "who": {"type": kind, "id": str(ident), "name": name},
                                  "why": "Marked lost soon after the visit" if lost_at else f"No follow-up for {COLD_DAYS} days after the visit"})
    users = users_map(set(per))
    total_v, total_c = sum(p["visits"] for p in per.values()), sum(p["cold"] for p in per.values())
    out = []
    for uid, p in per.items():
        rate = p["cold"] / p["visits"]
        ov, oc = total_v - p["visits"], total_c - p["cold"]
        team_rate = oc / ov if ov else None
        flagged = (team_rate is not None and p["visits"] >= VISIT_MIN and rate >= VISIT_RATE_MIN and rate >= team_rate + VISIT_GAP)
        p["examples"].sort(key=lambda e: e["visited_at"], reverse=True)
        out.append({"user": _person(users, uid), "visits": p["visits"], "cold": p["cold"], "cold_rate": round(rate, 3),
                    "team_cold_rate": round(team_rate, 3) if team_rate is not None else None, "flagged": flagged, "examples": p["examples"][:10]})
    out = [o for o in out if o["user"]]
    out.sort(key=lambda o: (not o["flagged"], -o["cold_rate"], -o["visits"]))
    return out


# ---- the radar -------------------------------------------------------------------------------

def run(ws, days: int = 7, now: dt.datetime | None = None) -> dict:
    end = now or utcnow()
    start = end - dt.timedelta(days=days)
    visit_days = max(days, VISIT_WINDOW_MIN)
    back = lost_leads_back(ws, start, end)
    reveals = reveal_outliers(ws, start, end)
    visits = cold_after_visits(ws, end, visit_days)
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat(), "days": days},
        "visit_range": {"from": (end - dt.timedelta(days=visit_days + COLD_DAYS)).isoformat(), "to": (end - dt.timedelta(days=COLD_DAYS)).isoformat(),
                        "cold_days": COLD_DAYS},
        "lost_came_back": back,
        "reveals": reveals,
        "visits": visits,
        "summary": {"lost_came_back": len(back), "via_backdoor": sum(1 for x in back if x["backdoor"]),
                    "reveal_flags": sum(1 for x in reveals if x["flagged"]), "visit_flags": sum(1 for x in visits if x["flagged"])},
    }


def summary_lines(r: dict) -> list[str]:
    """Plain sentences for the weekly report, most serious first."""
    lines = []
    back = r["lost_came_back"]
    if back:
        n, b = len(back), sum(1 for x in back if x["backdoor"])
        lines.append(f"{n} lead{'s' if n != 1 else ''} marked lost came back" + (f", {b} through a broker, walk-in or referral." if b else "."))
        for x in back[:3]:
            by = x["lost"]["marked_by"]["name"] if x["lost"]["marked_by"] else "someone"
            src = (x["back"]["source"] or "a new enquiry").replace("_", " ")
            lines.append(f"• {x['lost']['name']}: marked lost by {by}, back {x['gap_days']} days later via {src}.")
    for x in r["reveals"]:
        if x["flagged"]:
            usual = f"{x['team_usual']:g}" if x["team_usual"] is not None else "0"
            lines.append(f"{x['user']['name']} revealed {x['reveals']} phone numbers (the team's usual is {usual}); {x['not_their_clients']} weren't their clients.")
    for x in r["visits"]:
        if x["flagged"]:
            lines.append(f"{x['user']['name']}: {x['cold']} of {x['visits']} visited leads went cold after the site visit "
                         f"({round(x['cold_rate'] * 100)}% vs {round((x['team_cold_rate'] or 0) * 100)}% for the rest of the team).")
    return lines


def weekly_enabled(ws) -> bool:
    return bool((ws.settings or {}).get("leakage_report", True))


def send_weekly(ws, now: dt.datetime | None = None) -> int:
    """The owner's weekly report: an in-app notification and an email to owners and admins (each member's
    notification preferences decide which). Sent even when nothing was found, so silence never means "broken"."""
    import html

    from flask import current_app

    from app.models import Notification, User
    from app.services import email as email_service
    from app.services.notifications import prefs_for, workspace_admins

    r = run(ws.id, 7, now)
    lines = summary_lines(r)
    title = f"Lead leakage radar: {len([l for l in lines if not l.startswith('•')])} thing(s) to look at this week" if lines else "Lead leakage radar: nothing leaked this week"
    short = " ".join(lines)[:500] if lines else "No lost leads came back, no unusual phone reveals and no rep's visited leads went cold more than the team's."
    link = "/app/radar"
    parts, bullets = [], []
    for line in lines:
        if line.startswith("•"):
            bullets.append(f"<li>{html.escape(line[1:].strip())}</li>")
            continue
        if bullets:
            parts.append(f"<ul>{''.join(bullets)}</ul>")
            bullets = []
        parts.append(f"<p>{html.escape(line)}</p>")
    if bullets:
        parts.append(f"<ul>{''.join(bullets)}</ul>")
    body = f"<h1>{html.escape(title)}</h1>" + ("".join(parts) or f"<p>{html.escape(short)}</p>")
    body += f"<p><a class='btn' href='{current_app.config['WEB_ORIGIN']}{link}'>Open the radar</a></p>"
    sent = 0
    for uid in workspace_admins(ws.id):
        member = db.session.query(WorkspaceMember).filter_by(workspace_id=ws.id, user_id=uid, status="active").one_or_none()
        p = prefs_for(member, "leakage_report")
        if p.get("in_app", True):
            db.session.add(Notification(workspace_id=ws.id, user_id=uid, type="leakage_report", title=title[:200], body=short, link=link, data=r["summary"]))
        if p.get("email"):
            user = db.session.get(User, uid)
            if user:
                email_service.send_raw(user.email, title, email_service.LAYOUT.replace("{{ content }}", body), workspace_id=ws.id, template_key="notification.leakage_report")
        sent += 1
    ws.settings = {**(ws.settings or {}), "leakage_report_sent_at": (now or utcnow()).isoformat()}
    return sent
