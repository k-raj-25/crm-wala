"""Calling clients through the company number, so a client's number never reaches an employee's phone.

Every call goes through the connected calling provider (see services/telephony): the employee's own phone is rung from
the company number and bridged to the client, who also only ever sees the company number. When a client calls the
company number back, the call is rung through to whoever handles that lead (its owner), else to the workspace's
fallback person (the owner by default). Admins choose this in the calling settings.

A live call can be handed over: members with `calls.transfer_any` (Owner, Admin) to anyone in the team, everyone else
to their manager (`WorkspaceMember.reports_to`, else a more senior member of their team, else the owner). The
employee hangs up and the client, still on the line, is rung through to the colleague.

Call state lives on the existing `Call` row: status ringing -> in_progress -> completed | missed | failed, `user_id` is
whoever has the call now, and `data` keeps the hand-over history and a pending hand-over. Phone numbers are never put
in `data`, and `Call.phone` is masked for members who can't see numbers like everywhere else.
"""
from __future__ import annotations

import datetime as dt
import logging
import secrets
import uuid
from typing import Any

from flask import current_app, g

from app.core.errors import ApiError, forbidden
from app.core.permissions import has_permission
from app.extensions import db
from app.models import Call, Contact, Integration, Lead, User, Workspace, WorkspaceMember
from app.models.base import utcnow
from app.services import activities, audit, integrations, mailbox, notifications
from app.services.telephony import PROVIDERS, Dial, Leg, Provider, adapter
from app.services.whatsapp import find_record, normalize_phone

log = logging.getLogger("app.calling")

LIVE = ("ringing", "in_progress")
STALE_AFTER = dt.timedelta(hours=4)  # a live call we never heard the end of
HANDOVER_TIMEOUT = dt.timedelta(minutes=3)  # a hand-over the employee never hung up for
DEFAULT_ROUTING = {
    "inbound": "lead_owner",  # lead_owner: whoever handles the lead, else the fallback person | fallback: always the fallback person
    "fallback_user_id": None,  # None = the workspace owner
    "ring_fallback_too": True,  # when the lead's person doesn't pick up, ring the fallback person next
    "create_leads": True,  # a number we don't know becomes a new lead
    "record": True,
    "ring_seconds": 30,
    "client_first": False,  # outgoing calls ring the client first (needs the call flow; makes outgoing calls transferable)
    "greeting": True,  # "Connecting you to Priya" to the client while their person is rung
}


# ---- connection & settings ---------------------------------------------------------------------------------------

def find_connection(workspace_id) -> Integration | None:
    rows = db.session.query(Integration).filter(Integration.workspace_id == workspace_id, Integration.provider.in_(list(PROVIDERS)),
                                                Integration.status.in_(("connected", "error")), Integration.credentials_enc.isnot(None)).all()
    return rows[0] if rows else None


def connection(workspace_id) -> tuple[Integration, Provider]:
    i = find_connection(workspace_id)
    if i is None:
        raise ApiError(409, "calling_not_connected", "Calling isn't set up yet. An admin can connect Exotel in Integrations.")
    return i, adapter(i.provider)


def routing(i: Integration) -> dict:
    return {**DEFAULT_ROUTING, **((i.config or {}).get("routing") or {})}


def creds_for(i: Integration) -> dict:
    return {**integrations.get_creds(i), "client_first": routing(i)["client_first"]}


def new_webhook_config() -> dict:
    return {"webhook_token": secrets.token_urlsafe(24)}


def webhook_url(i: Integration, hook: str) -> str:
    return f"{current_app.config['WEB_ORIGIN']}/api/v1/inbound/calls/{(i.config or {}).get('webhook_token', '')}/{hook}"


def integration_for_token(token: str) -> Integration | None:
    if not token or len(token) < 16:
        return None
    return db.session.query(Integration).filter(Integration.provider.in_(list(PROVIDERS)), Integration.config["webhook_token"].astext == token).first()


# ---- people ------------------------------------------------------------------------------------------------------

def _active_members(workspace_id) -> list[WorkspaceMember]:
    return db.session.query(WorkspaceMember).filter_by(workspace_id=workspace_id, status="active").all()


def member_phone(workspace_id, user_id) -> str | None:
    """The employee's own phone (from their profile), only while they're an active member of this workspace."""
    if not user_id:
        return None
    row = db.session.query(User.phone).join(WorkspaceMember, WorkspaceMember.user_id == User.id) \
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id, WorkspaceMember.status == "active").first()
    return normalize_phone(row[0]) if row and row[0] else None


def fallback_user(i: Integration) -> uuid.UUID:
    ws = db.session.get(Workspace, i.workspace_id)
    fid = routing(i).get("fallback_user_id")
    if fid:
        try:
            fid = uuid.UUID(str(fid))
        except ValueError:
            fid = None
    if fid and member_phone(i.workspace_id, fid):
        return fid
    return ws.owner_id


def managers_of(workspace_id, user_id) -> list[uuid.UUID]:
    """Who this member can hand a call to: their manager, else more senior people in their team, and always the owner."""
    members = {m.user_id: m for m in _active_members(workspace_id)}
    me = members.get(user_id)
    owner_id = db.session.get(Workspace, workspace_id).owner_id
    out: list[uuid.UUID] = []
    if me is not None:
        if me.reports_to and me.reports_to in members:
            out.append(me.reports_to)
        elif me.team_id:
            out += [m.user_id for m in members.values() if m.team_id == me.team_id and m.user_id != user_id and m.role.rank > me.role.rank]
    if owner_id != user_id and owner_id not in out:
        out.append(owner_id)
    return out


def can_transfer_any(perms) -> bool:
    return has_permission(perms, "calls.transfer_any")


def transfer_targets(workspace_id, user_id, perms) -> list[dict]:
    members = {m.user_id: m for m in _active_members(workspace_id)}
    ids = [uid for uid in members if uid != user_id] if can_transfer_any(perms) else managers_of(workspace_id, user_id)
    users = {u.id: u for u in db.session.query(User).filter(User.id.in_(ids or [uuid.uuid4()]))}
    out = []
    for uid in ids:
        u, m = users.get(uid), members.get(uid)
        if u is None or m is None:
            continue
        out.append({"user_id": str(uid), "name": u.name, "role": m.role.name, "avatar_url": u.avatar_url, "has_phone": bool(normalize_phone(u.phone) if u.phone else None)})
    return sorted(out, key=lambda r: (not r["has_phone"], r["name"].lower())) if can_transfer_any(perms) else out


# ---- outgoing calls ----------------------------------------------------------------------------------------------

def _name(uid) -> str:
    u = db.session.get(User, uid) if uid else None
    return u.name if u else "a colleague"


def _entity_links(etype: str, entity) -> dict:
    links = activities.links_for(etype, entity)
    return {k: links.get(k) for k in ("lead_id", "contact_id", "company_id", "deal_id")}


def place_call(etype: str, entity: Lead | Contact) -> Call:
    """Ring the current member's phone from the company number and bridge them to the client."""
    i, p = connection(g.workspace.id)
    agent = member_phone(g.workspace.id, g.user.id)
    if not agent:
        raise ApiError(422, "calling_no_phone", "Add your mobile number in Settings → Profile first. The CRM rings you on it, then connects the client.")
    client = normalize_phone(entity.phone)
    if not client:
        raise ApiError(422, "calling_no_client_phone", f"{entity.name} has no phone number saved.")
    if client == agent:
        raise ApiError(422, "validation_error", "That's your own number.")
    r = routing(i)
    call = Call(workspace_id=g.workspace.id, direction="outbound", status="ringing", phone=entity.phone, occurred_at=utcnow(), user_id=g.user.id,
                provider=i.provider, data={"via": "company_number", "agents": [str(g.user.id)], "transfers": []}, **_entity_links(etype, entity))
    db.session.add(call)
    db.session.flush()
    call.provider_call_id = p.start_call(creds_for(i), agent=agent, client=client, status_url=webhook_url(i, "status"), record=r["record"],
                                         ring_seconds=int(r["ring_seconds"]), ref=str(call.id))
    i.last_synced_at = utcnow()
    return call


# ---- live calls --------------------------------------------------------------------------------------------------

def _expire(call: Call) -> bool:
    """End a call we never heard back about (a provider webhook lost, or a hand-over nobody hung up for)."""
    now = utcnow()
    pending = (call.data or {}).get("pending_transfer")
    if pending and dt.datetime.fromisoformat(pending["at"]) < now - HANDOVER_TIMEOUT:
        data = dict(call.data)
        data.pop("pending_transfer", None)
        call.data = data
    if (call.occurred_at or call.created_at) < now - STALE_AFTER:
        finish(call, "completed" if call.status == "in_progress" else "missed")
        return True
    return False


def active_calls(workspace_id, user_id) -> list[Call]:
    rows = db.session.query(Call).filter(Call.workspace_id == workspace_id, Call.user_id == user_id, Call.status.in_(LIVE), Call.provider.isnot(None),
                                         Call.deleted_at.is_(None)).order_by(Call.created_at.desc()).limit(5).all()
    return [c for c in rows if not _expire(c)]


def live_call(workspace_id, call_id) -> Call:
    c = db.session.query(Call).filter(Call.id == call_id, Call.workspace_id == workspace_id, Call.deleted_at.is_(None)).one_or_none()
    if c is None or c.status not in LIVE or not c.provider or _expire(c):
        raise ApiError(409, "call_not_live", "This call has already ended.")
    return c


def request_transfer(call: Call, to_user_id: uuid.UUID) -> dict:
    """Mark the call to be handed to a colleague. The employee then hangs up and the client is rung through to them."""
    ws_id = g.workspace.id
    if call.user_id != g.user.id:
        raise forbidden("Only the person on the call can hand it over.", "not_on_call")
    i, p = connection(ws_id)
    if not p.can_transfer(creds_for(i), call.direction):
        raise ApiError(409, "transfer_unsupported", "Outgoing calls can't be handed over with your current calling setup. "
                       "An admin can turn on “Ring the client first” in calling settings.")
    allowed = {uuid.UUID(t["user_id"]) for t in transfer_targets(ws_id, g.user.id, g.permissions)}
    if to_user_id not in allowed:
        raise forbidden("You can hand calls only to your manager." if not can_transfer_any(g.permissions) else "That person isn't an active member.",
                        "transfer_not_allowed")
    if not member_phone(ws_id, to_user_id):
        raise ApiError(422, "calling_no_phone", f"{_name(to_user_id)} has no mobile number on their profile, so the call can't ring them.")
    call.data = {**(call.data or {}), "pending_transfer": {"to": str(to_user_id), "by": str(g.user.id), "at": utcnow().isoformat()}}
    audit.record("call.transfer_requested", entity_type="call", entity_id=call.id, summary=f"Handing a call to {_name(to_user_id)}")
    return {"to": {"user_id": str(to_user_id), "name": _name(to_user_id)}}


def cancel_transfer(call: Call) -> None:
    if call.user_id != g.user.id:
        raise forbidden("Only the person on the call can change this.", "not_on_call")
    data = dict(call.data or {})
    data.pop("pending_transfer", None)
    call.data = data


def serialize_live(c: Call) -> dict:
    from app.services import privacy

    etype, entity = _record_of(c)
    data = c.data or {}
    pending = data.get("pending_transfer")
    i = find_connection(c.workspace_id)
    can = bool(i) and adapter(i.provider).can_transfer(creds_for(i), c.direction)
    return {"id": str(c.id), "direction": c.direction, "status": c.status, "started_at": (c.occurred_at or c.created_at).isoformat(),
            "answered_at": data.get("answered_at"), "phone": privacy.mask_value(c.phone),
            "record": {"type": etype, "id": str(entity.id), "name": entity.name} if entity else None,
            "can_transfer": can, "pending_transfer": {"to": pending["to"], "name": _name(uuid.UUID(pending["to"]))} if pending else None,
            "transferred_from": data["transfers"][-1]["from_name"] if data.get("transfers") else None}


def _record_of(c: Call) -> tuple[str | None, Any]:
    if c.contact_id:
        return "contact", db.session.get(Contact, c.contact_id)
    if c.lead_id:
        return "lead", db.session.get(Lead, c.lead_id)
    return None, None


# ---- provider webhooks -------------------------------------------------------------------------------------------

def _by_sid(i: Integration, sid: str) -> Call | None:
    return db.session.query(Call).filter(Call.workspace_id == i.workspace_id, Call.provider == i.provider, Call.provider_call_id == sid).first()


def _who_has(i: Integration, numbers: list[str]) -> uuid.UUID | None:
    for m in _active_members(i.workspace_id):
        if m.user and m.user.phone and normalize_phone(m.user.phone) in numbers:
            return m.user_id
    return None


def _ring_list(i: Integration, first: uuid.UUID | None) -> list[uuid.UUID]:
    r = routing(i)
    out: list[uuid.UUID] = []
    if first and member_phone(i.workspace_id, first):
        out.append(first)
    fb = fallback_user(i)
    if (not out or r["ring_fallback_too"]) and fb not in out and member_phone(i.workspace_id, fb):
        out.append(fb)
    return out


def _new_inbound(i: Integration, leg: Leg) -> Call | None:
    ws_id, r = i.workspace_id, routing(i)
    caller = leg.from_number
    if not caller:
        return None
    found = find_record(ws_id, caller)
    if found is None and r["create_leads"]:
        lead = Lead(workspace_id=ws_id, first_name="Caller", last_name=caller[-4:], phone=f"+{caller}", source="call", status="new", tags=["phone-call"])
        db.session.add(lead)
        db.session.flush()
        activities.log_activity("created", "Lead created from a call to the company number", workspace_id=ws_id, lead_id=lead.id, user_id=None)
        audit.record("lead.created", entity_type="lead", entity_id=lead.id, workspace_id=ws_id, actor_type="system", actor_label="Calls",
                     summary=f"Lead “{lead.name}” created from a phone call")
        found = ("lead", lead)
    handler = found[1].owner_id if found and r["inbound"] == "lead_owner" else None
    ring = _ring_list(i, handler)
    links = _entity_links(*found) if found else {}
    call = Call(workspace_id=ws_id, direction="inbound", status="ringing", phone=f"+{caller}", occurred_at=utcnow(), user_id=ring[0] if ring else None,
                provider=i.provider, provider_call_id=leg.call_sid, data={"via": "company_number", "agents": [str(u) for u in ring], "transfers": []}, **links)
    db.session.add(call)
    db.session.flush()
    if found and ring:
        etype, entity = found
        path = f"/app/{'contacts' if etype == 'contact' else 'leads'}/{entity.id}"
        notifications.notify(ws_id, ring[:1], "call", f"Incoming call: {entity.name}", "Pick up your phone. The call comes from the company number.", path)
    return call


def handle_connect(i: Integration, leg: Leg) -> Dial | None:
    """The call flow asks who to ring: a new inbound call, an outbound call rung client-first, or a hand-over."""
    r = routing(i)
    call = _by_sid(i, leg.call_sid)
    if call is None:
        if leg.raw.get("CustomField"):  # an outgoing client-first call we placed; the sid is already on it
            try:
                call = db.session.query(Call).filter(Call.workspace_id == i.workspace_id, Call.id == uuid.UUID(leg.raw["CustomField"])).first()
            except ValueError:
                call = None
        call = call or _new_inbound(i, leg)
    if call is None:
        return None
    ring = [call.user_id] if call.direction == "outbound" or (call.data or {}).get("transfers") else (
        [uuid.UUID(a) for a in (call.data or {}).get("agents", [])] or _ring_list(i, call.user_id))
    if call.direction == "inbound" and (call.data or {}).get("transfers") and r["ring_fallback_too"]:
        # a hand-over nobody picks up goes back to the person who handed it over
        back = uuid.UUID(call.data["transfers"][-1]["from"])
        ring.append(back)
    numbers = [n for n in (member_phone(i.workspace_id, u) for u in ring) if n]
    if not numbers:
        log.warning("call %s: nobody to ring", call.id)
        finish(call, "missed")
        return None
    greeting = None
    if r["greeting"]:
        name = _name(ring[0]).split(" ")[0]
        greeting = f"Please hold, connecting you to {name}." if call.direction == "inbound" or (call.data or {}).get("transfers") \
            else f"Hello, please hold while we connect you to {name}."
    return Dial(numbers=numbers, caller_id=integrations.get_creds(i).get("exophone", ""), record=r["record"], ring_seconds=int(r["ring_seconds"]),
                greeting=greeting, status_url=webhook_url(i, "status"))


def handle_handover(i: Integration, leg: Leg) -> bool:
    """Runs when the employee's leg ends. If they asked to hand the call over, move it to the colleague and tell the flow to
    ring again; otherwise the call is over."""
    call = _by_sid(i, leg.call_sid)
    if call is None:
        return False
    _add_leg(call, leg)
    data = dict(call.data or {})
    pending = data.pop("pending_transfer", None)
    if pending and dt.datetime.fromisoformat(pending["at"]) >= utcnow() - HANDOVER_TIMEOUT:
        to = uuid.UUID(pending["to"])
        frm = call.user_id
        data["transfers"] = [*data.get("transfers", []), {"from": str(frm), "from_name": _name(frm), "to": str(to), "at": utcnow().isoformat()}]
        data["agents"] = [*data.get("agents", []), str(to)]
        data.pop("answered_at", None)
        call.data, call.user_id, call.status = data, to, "ringing"
        etype, entity = _record_of(call)
        activities.log_activity("call", f"Call handed from {_name(frm)} to {_name(to)}", workspace_id=i.workspace_id, user_id=frm,
                                data={"call_id": str(call.id)}, touch=False, **({k: getattr(call, k) for k in ("lead_id", "contact_id", "company_id", "deal_id")}))
        notifications.notify(i.workspace_id, [to], "call", f"{_name(frm)} is handing you a call" + (f": {entity.name}" if entity else ""),
                             "Pick up your phone. The call comes from the company number.",
                             f"/app/{'contacts' if etype == 'contact' else 'leads'}/{entity.id}" if entity else None)
        return True
    call.data = data
    finish(call, "completed" if data.get("answered_at") or (leg.status == "completed" and (leg.duration or 0) > 0) else "missed")
    return False


def handle_status(i: Integration, leg: Leg) -> None:
    call = _by_sid(i, leg.call_sid)
    if call is None or call.status not in LIVE:
        return
    data = dict(call.data or {})
    agent_no = member_phone(i.workspace_id, call.user_id)
    if leg.answered_number and agent_no and leg.answered_number != agent_no:
        if call.direction == "inbound" and not data.get("transfers"):
            # the fallback person picked up instead of the lead's person: the call is theirs now
            who = _who_has(i, [leg.answered_number])
            if who:
                call.user_id = who
        else:
            return  # news about an earlier leg of a handed-over call
    if leg.status == "in_progress":
        data.setdefault("answered_at", utcnow().isoformat())
        call.data, call.status = data, "in_progress"
        return
    if leg.status in ("completed", "missed", "failed"):
        if data.get("pending_transfer"):
            return  # the employee hung up to hand the call over; the flow's hand-over step decides what happens next
        if data.get("transfers") and not leg.answered_number and \
                dt.datetime.fromisoformat(data["transfers"][-1]["at"]) > utcnow() - dt.timedelta(seconds=30):
            return  # can't tell which leg this is about, and a hand-over just happened
        _add_leg(call, leg)
        answered = bool(call.data.get("answered_at")) or (leg.duration or 0) > 0
        finish(call, "completed" if answered and leg.status != "failed" else ("failed" if leg.status == "failed" else "missed"))


def _add_leg(call: Call, leg: Leg) -> None:
    if leg.duration:
        call.duration_seconds = (call.duration_seconds or 0) + leg.duration
    if leg.recording_url and leg.recording_url.startswith("https://"):
        call.recording_url = leg.recording_url[:500]


def finish(call: Call, status: str) -> None:
    if call.status not in LIVE:
        return
    call.status = status
    call.outcome = call.outcome or ("connected" if status == "completed" else "no_answer")
    data = dict(call.data or {})
    data.pop("pending_transfer", None)
    data["ended_at"] = utcnow().isoformat()
    call.data = data
    etype, entity = _record_of(call)
    who = _name(call.user_id) if call.user_id else None
    dur = f" ({call.duration_seconds // 60}m {call.duration_seconds % 60}s)" if call.duration_seconds else ""
    if call.direction == "inbound":
        title = f"Call from client answered by {who}{dur}" if status == "completed" else "Missed call from client"
    else:
        title = f"Call by {who}{dur}" if status == "completed" else f"Call by {who}: no answer"
    links = {k: getattr(call, k) for k in ("lead_id", "contact_id", "company_id", "deal_id")}
    activities.log_activity("call", title, workspace_id=call.workspace_id, user_id=call.user_id, occurred_at=call.occurred_at,
                            data={"call_id": str(call.id), "outcome": call.outcome, "direction": call.direction}, **links)
    if status == "completed":
        mailbox.touch_contacted(call, call.occurred_at or utcnow())
    elif call.direction == "inbound" and entity is not None:
        targets = [entity.owner_id] if entity.owner_id else notifications.workspace_admins(call.workspace_id)
        notifications.notify(call.workspace_id, targets, "call", f"Missed call: {entity.name}", "Call them back from the CRM. They'll see the company number.",
                             f"/app/{'contacts' if etype == 'contact' else 'leads'}/{entity.id}")

