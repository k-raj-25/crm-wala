"""Family and NRI mode: family members on a buyer, messages in their language and time zone, AED/USD prices, the NRI
document checklist, and video walkthroughs they can ask for from their own page."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from flask import Blueprint, g, request
from pydantic import EmailStr, Field

from app.core.auth import protect, require
from app.core.errors import ApiError, bad_request, conflict, forbidden, not_found
from app.core.responses import created, no_content, ok
from app.core.tenant import bypass_scope, set_tenant
from app.extensions import db, limiter
from app.models import FamilyMember, FamilyMessage, Meeting, Walkthrough, Workspace
from app.models.base import utcnow
from app.schemas.common import Schema, parse, patchify, provided
from app.services import activities, audit, integrations, privacy
from app.services import family as svc

bp = Blueprint("family", __name__, url_prefix="/api/v1/family")
link_bp = Blueprint("family_link", __name__, url_prefix="/api/v1/public/family")

Relation = Literal["spouse", "father", "mother", "son", "daughter", "brother", "sister", "father_in_law", "mother_in_law", "son_in_law", "daughter_in_law", "other"]
Role = Literal["decides", "pays", "advises"]
Currency = Literal["INR", "AED", "USD"]


class MemberIn(Schema):
    record: str = Field(min_length=3, max_length=60)  # "lead:<id>" | "contact:<id>" | "deal:<id>"
    name: str = Field(min_length=1, max_length=120)
    relation: Relation = "other"
    role: Role = "decides"
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    language: str = Field(default="en", max_length=8)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    city: str | None = Field(default=None, max_length=80)
    is_nri: bool = False
    currency: Currency = "INR"
    notes: str | None = Field(default=None, max_length=2000)


MemberPatch = patchify(MemberIn, "MemberPatch")


def _record(raw: str):
    entity, _, ident = (raw or "").partition(":")
    try:
        ident = uuid.UUID(ident)
    except ValueError:
        raise bad_request("Choose a lead, client or deal")
    if entity not in ("lead", "contact", "deal"):
        raise bad_request("Choose a lead, client or deal")
    require(f"{entity}s.read")
    return entity, svc.get_record(entity, ident)


def _member(ident, *, edit: bool = False) -> FamilyMember:
    m = db.session.query(FamilyMember).filter(FamilyMember.id == ident, FamilyMember.workspace_id == g.workspace.id, FamilyMember.deleted_at.is_(None)).one_or_none()
    if m is None:
        raise not_found("Family member")
    entity, _rec = svc.buyer_of(m)
    require(f"{entity}s.{'update' if edit else 'read'}")
    return m


def _check(d: dict) -> dict:
    if "language" in d and d["language"] not in svc.LANGUAGES:
        raise ApiError(422, "validation_error", "Pick a language from the list", {"language": "Unknown language"})
    if "timezone" in d and not svc.valid_timezone(d["timezone"]):
        raise ApiError(422, "validation_error", "Pick a time zone from the list", {"timezone": "Unknown time zone"})
    return d


def _one(m: FamilyMember) -> dict:
    return svc.serialize([m])[0]


@bp.get("")
@protect()
def list_members():
    entity, rec = _record(request.args.get("record", ""))
    members = svc.members_for(entity, rec.id)
    return ok({"members": svc.serialize(members), "fx": svc.fx_meta(), "options": svc.options(), "can_edit": _can(f"{entity}s.update"), "can_message": _can("emails.create") and "whatsapp_integration" in g.features,
               "can_view_phones": privacy.can_view(), "can_reveal": privacy.can_reveal(), "is_owner": _owner()})


def _can(perm: str) -> bool:
    from app.core.permissions import has_permission

    return has_permission(g.permissions, perm)


def _owner() -> bool:
    return bool(getattr(g, "member", None) and g.member.role.key == "owner")


@bp.post("")
@protect()
def create_member():
    d = parse(MemberIn)
    entity, rec = _record(d.record)
    require(f"{entity}s.update")
    data = _check(d.model_dump(exclude={"record"}))
    data["email"] = str(data["email"]) if data.get("email") else None
    if len(svc.members_for(entity, rec.id)) >= 12:
        raise conflict("A buyer can have up to 12 family members.")
    m = FamilyMember(workspace_id=g.workspace.id, created_by=g.user.id, **{f"{entity}_id": rec.id}, **data)
    db.session.add(m)
    db.session.flush()
    activities.log_activity("system", f"Added {svc.describe(m, rec.name)} to the family", body=f"{svc.ROLES[m.role]} · {svc.LANGUAGES[m.language][0]} · {m.timezone}",
                            data={"family_member_id": str(m.id)}, **svc.links(m))
    audit.record("family.created", entity_type=entity, entity_id=rec.id, summary=f"Added family member {svc.describe(m, rec.name)}")
    db.session.commit()
    return created(_one(m))


@bp.patch("/<uuid:ident>")
@protect()
def update_member(ident):
    m = _member(ident, edit=True)
    ch = _check({k: v for k, v in provided(parse(MemberPatch)).items() if k != "record"})
    if "email" in ch and ch["email"] is not None:
        ch["email"] = str(ch["email"])
    if "phone" in ch and not privacy.can_view():  # same rule as the buyer's number: a hidden number can't be wiped or overwritten
        v = ch["phone"]
        if v in (None, "") or privacy.is_masked(v) or v == m.phone:
            ch.pop("phone")
        elif m.phone:
            raise forbidden("Only someone who can see phone numbers can change a saved number.", "phone_hidden")
    for k in ("name", "relation", "role", "language", "timezone", "is_nri", "currency"):
        if k in ch and ch[k] is None:
            ch.pop(k)
    for k, v in ch.items():
        setattr(m, k, v)
    db.session.commit()
    return ok(_one(m))


@bp.delete("/<uuid:ident>")
@protect()
def delete_member(ident):
    m = _member(ident, edit=True)
    m.deleted_at = utcnow()
    m.link_token = None  # their page stops working
    db.session.query(FamilyMessage).filter(FamilyMessage.member_id == m.id, FamilyMessage.status == "scheduled").update({"status": "cancelled"}, synchronize_session=False)
    activities.log_activity("system", f"Removed {svc.describe(m)} from the family", data={"family_member_id": str(m.id)}, touch=False, **svc.links(m))
    db.session.commit()
    return no_content()


@bp.post("/<uuid:ident>/reveal-phone")
@protect()
def reveal_phone(ident):
    m = _member(ident)
    if not privacy.can_reveal():
        raise forbidden("Your role can't see clients' phone numbers.", "phone_hidden")
    if not privacy.can_view():
        entity, rec = svc.buyer_of(m)
        audit.record("phone.revealed", entity_type=entity, entity_id=rec.id if rec else None, summary=f"Viewed the phone number of {svc.describe(m)}")
        db.session.commit()
    return ok({"phone": m.phone})


class ChecklistIn(Schema):
    item: str = Field(max_length=40)
    done: bool


@bp.put("/<uuid:ident>/checklist")
@protect()
def tick(ident):
    m = _member(ident, edit=True)
    d = parse(ChecklistIn)
    if d.item not in svc.CHECKLIST_KEYS:
        raise bad_request("Unknown document")
    items = dict(m.checklist or {})
    if d.done:
        items[d.item] = {"at": utcnow().isoformat(), "by": str(g.user.id)}
    else:
        items.pop(d.item, None)
    m.checklist = items
    db.session.commit()
    return ok(_one(m))


@bp.post("/<uuid:ident>/link")
@protect()
def make_link(ident):
    """Create (or, with ?rotate=1, replace) the member's own page link."""
    m = _member(ident, edit=True)
    if not m.link_token or request.args.get("rotate"):
        m.link_token = svc.new_token()
        audit.record("family.link", entity_type="family_member", entity_id=m.id, summary=f"Made a page link for {svc.describe(m)}")
        db.session.commit()
    return ok({"link": svc.link_url(m)})


# ---- messages ------------------------------------------------------------------------------------------------------

@bp.get("/<uuid:ident>/messages")
@protect("activities.read")
def messages(ident):
    from app.services import whatsapp

    m = _member(ident)
    phone = whatsapp.normalize_phone(m.phone)
    i = integrations.get(g.workspace.id, "whatsapp")
    queued = db.session.query(FamilyMessage).filter(FamilyMessage.member_id == m.id, FamilyMessage.status.in_(("scheduled", "failed"))) \
        .order_by(FamilyMessage.send_at).all()
    return ok({"connected": bool(i and i.status in ("connected", "error")), "has_phone": bool(phone),
               "window_open": bool(phone) and whatsapp.window_open(g.workspace.id, phone),
               "messages": [{**w.to_dict(), "phone": privacy.mask_value(f"+{w.phone}")} for w in svc.member_messages(m)],
               "queued": [{**q.to_dict(), "local_label": svc.local_label(q.send_at, m.timezone)} for q in queued]})


class TranslateIn(Schema):
    text: str = Field(min_length=1, max_length=3000)


@bp.post("/<uuid:ident>/translate")
@protect("emails.create")
@limiter.limit("120 per hour")
def translate(ident):
    m = _member(ident)
    out = svc.translate(parse(TranslateIn).text, m.language)
    db.session.commit()  # keeps the AI usage row
    return ok(out)


class DraftIn(Schema):
    kind: Literal["prices", "checklist", "link", "hello"] = "hello"


@bp.post("/<uuid:ident>/draft")
@protect("emails.create")
def draft(ident):
    m = _member(ident)
    kind = parse(DraftIn).kind
    if kind == "link" and not m.link_token:
        require(f"{svc.buyer_of(m)[0]}s.update")
        m.link_token = svc.new_token()
        db.session.commit()
    return ok({"text": svc.draft(m, kind)})


class TemplateIn(Schema):
    name: str = Field(min_length=1, max_length=120)
    language: str = Field(min_length=2, max_length=15)
    params: list[str] = Field(default_factory=list, max_length=10)


class SendIn(Schema):
    text: str | None = Field(default=None, max_length=4096)
    original: str | None = Field(default=None, max_length=4096)  # what the rep typed, when `text` is its translation
    template: TemplateIn | None = None
    when: Literal["now", "morning"] = "now"


@bp.post("/<uuid:ident>/messages")
@protect("emails.create")
@limiter.limit("120 per hour")
def send(ident):
    """Send a message to one family member now, or hold it until 9 am where they live."""
    from app.services import whatsapp

    if "whatsapp_integration" not in g.features:
        raise ApiError(402, "feature_unavailable", "WhatsApp isn't included in your current plan.", {"feature": "whatsapp_integration"})
    m = _member(ident)
    d = parse(SendIn)
    if bool(d.text and d.text.strip()) == bool(d.template):
        raise bad_request("Send a message or a template")
    i = whatsapp.connection(g.workspace.id)
    template = None
    if d.template:
        t = {(x["name"], x["language"]): x for x in whatsapp.list_templates(i)}.get((d.template.name, d.template.language))
        if t is None:
            raise ApiError(422, "whatsapp_template_missing", "That template isn't approved for this number or language.")
        if not t["supported"] or t["header"] in ("DOCUMENT", "IMAGE"):
            raise ApiError(422, "whatsapp_template_unsupported", "Pick a text template.")
        if len(d.template.params) != t["body_params"] or any(not p.strip() for p in d.template.params):
            raise ApiError(422, "validation_error", f"Fill in all {t['body_params']} placeholders in the template.", {"params": "Incomplete"})
        template = {k: t[k] for k in ("name", "language", "body", "param_names")} | {"params": d.template.params}
        body = whatsapp._render(t["body"], t["param_names"], d.template.params)
    else:
        body = d.text.strip()
    send_at = svc.next_morning(m.timezone) if d.when == "morning" else utcnow()
    fm = FamilyMessage(workspace_id=g.workspace.id, member_id=m.id, status="scheduled", body=body, template=template, language=m.language,
                       original=d.original if d.original and d.original.strip() != body else None, send_at=send_at, user_id=g.user.id)
    db.session.add(fm)
    db.session.flush()
    if d.when == "now":
        svc.deliver(fm)  # errors roll the queued row back with the request
    else:
        activities.log_activity("whatsapp", f"WhatsApp to {svc.describe(m)} scheduled for {svc.local_label(send_at, m.timezone)}", body=body[:2000],
                                data={"family_member_id": str(m.id), "family_message_id": str(fm.id)}, touch=False, **svc.links(m))
    db.session.commit()
    return created({**fm.to_dict(), "local_label": svc.local_label(send_at, m.timezone)})


@bp.delete("/messages/<uuid:ident>")
@protect("emails.create")
def cancel_message(ident):
    fm = db.session.query(FamilyMessage).filter(FamilyMessage.id == ident, FamilyMessage.workspace_id == g.workspace.id).one_or_none()
    if fm is None:
        raise not_found("Message")
    _member(fm.member_id)
    if fm.status not in ("scheduled", "failed"):
        raise conflict("This message has already gone out.")
    fm.status = "cancelled"
    db.session.commit()
    return no_content()


# ---- video walkthroughs --------------------------------------------------------------------------------------------

class WalkthroughIn(Schema):
    starts_at: str = Field(min_length=10, max_length=40)  # local wall time in the member's zone, or ISO with an offset
    note: str | None = Field(default=None, max_length=500)


@bp.post("/<uuid:ident>/walkthroughs")
@protect("meetings.create")
def request_walkthrough(ident):
    m = _member(ident)
    d = parse(WalkthroughIn)
    w = svc.new_walkthrough(m, svc.parse_local(d.starts_at, m.timezone), via="rep", note=d.note)
    db.session.commit()
    return created(svc.walkthrough_view(w))


def _walkthrough(ident) -> tuple[Walkthrough, FamilyMember]:
    w = db.session.query(Walkthrough).filter(Walkthrough.id == ident, Walkthrough.workspace_id == g.workspace.id).one_or_none()
    if w is None:
        raise not_found("Walkthrough")
    return w, _member(w.member_id)


class ConfirmIn(Schema):
    meeting_url: str = Field(min_length=8, max_length=500, pattern=r"^https://\S+$")
    starts_at: str | None = Field(default=None, max_length=40)  # move it to another time while confirming
    minutes: int = Field(default=45, ge=15, le=180)
    notify: bool = True


@bp.post("/walkthroughs/<uuid:ident>/confirm")
@protect("meetings.create")
def confirm_walkthrough(ident):
    """Confirm with a meeting link: it goes on the calendar, and the member is told the time where they live, in their language."""
    w, m = _walkthrough(ident)
    if w.status != "requested":
        raise conflict(f"This walkthrough is already {w.status}.")
    d = parse(ConfirmIn)
    if d.starts_at:
        w.starts_at = svc.parse_local(d.starts_at, w.timezone)
        svc.check_slot(w.starts_at)
    entity, rec = svc.buyer_of(m)
    meeting = Meeting(workspace_id=g.workspace.id, title=f"Video walkthrough: {svc.describe(m)}", starts_at=w.starts_at, ends_at=w.starts_at + dt.timedelta(minutes=d.minutes),
                      meeting_url=d.meeting_url, organizer_id=g.user.id, kind="meeting", project_id=w.project_id, unit_id=w.unit_id, status="scheduled",
                      description=w.note, attendees=[{"name": m.name, **({"email": m.email} if m.email else {})}], **svc.links(m))
    db.session.add(meeting)
    db.session.flush()
    w.status, w.meeting_url, w.meeting_id, w.decided_by, w.decided_at = "confirmed", d.meeting_url, meeting.id, g.user.id, utcnow()
    activities.log_activity("meeting", f"Video walkthrough confirmed with {svc.describe(m)}", body=svc.local_label(w.starts_at, w.timezone),
                            data={"walkthrough_id": str(w.id), "meeting_id": str(meeting.id), "family_member_id": str(m.id)}, **svc.links(m))
    first = m.name.split(" ")[0]
    english = f"Hi {first}, your video walkthrough is confirmed for {svc.local_label(w.starts_at, w.timezone)}. Join here: {d.meeting_url}\n\n{g.user.name.split(' ')[0]}"
    out = {"walkthrough": svc.walkthrough_view(w), "message": english, "sent": False, "reason": None}
    if d.notify:
        msg = svc.translate(english, m.language)
        out["message"] = msg["text"]
        fm = FamilyMessage(workspace_id=g.workspace.id, member_id=m.id, status="scheduled", body=msg["text"], language=m.language,
                           original=english if msg["ai"] else None, send_at=utcnow(), user_id=g.user.id)
        db.session.add(fm)
        db.session.flush()
        try:
            with db.session.begin_nested():
                if "whatsapp_integration" not in g.features:
                    raise ApiError(402, "feature_unavailable", "WhatsApp isn't in your plan.")
                svc.deliver(fm)
            out["sent"] = True
        except ApiError as e:  # still confirmed: the rep copies the message and sends it another way
            fm.status, fm.error = "cancelled", e.message[:400]
            out["reason"] = e.message
        if m.email:
            from app.services import email as email_service

            html = "<p>" + msg["text"].replace("\n", "<br>") + f"</p><p><a class='btn' href='{d.meeting_url}'>Join the walkthrough</a></p>"
            email_service.send_raw(m.email, "Your video walkthrough is confirmed", email_service.LAYOUT.replace("{{ content }}", html), workspace_id=g.workspace.id,
                                   template_key="family.walkthrough")
            out["emailed"] = True
    db.session.commit()
    return ok(out)


@bp.post("/walkthroughs/<uuid:ident>/cancel")
@protect("meetings.create")
def cancel_walkthrough(ident):
    w, m = _walkthrough(ident)
    if w.status == "cancelled":
        raise conflict("This walkthrough is already cancelled.")
    w.status, w.decided_by, w.decided_at = "cancelled", g.user.id, utcnow()
    if w.meeting_id:
        meeting = db.session.get(Meeting, w.meeting_id)
        if meeting:
            meeting.status = "canceled"
    activities.log_activity("meeting", f"Video walkthrough with {svc.describe(m)} cancelled", data={"walkthrough_id": str(w.id)}, touch=False, **svc.links(m))
    db.session.commit()
    return ok(svc.walkthrough_view(w))


# ---- exchange rates ------------------------------------------------------------------------------------------------

class RatesIn(Schema):
    AED: float | None = Field(default=None, gt=1, lt=1000)
    USD: float | None = Field(default=None, gt=1, lt=1000)


@bp.get("/settings")
@protect()
def get_rates():
    return ok({**svc.fx_meta(), "is_owner": _owner()})


@bp.put("/settings")
@protect("settings.manage")
def put_rates():
    """The rupee rate for AED and USD prices. The owner sets it, so a quoted price doesn't move with the market overnight."""
    if not _owner():
        raise forbidden("Only the workspace owner can set exchange rates.", "owner_only")
    d = parse(RatesIn)
    before = svc.rates()
    new = {c: round(v, 4) for c, v in d.model_dump().items() if v}
    g.workspace.settings = {**(g.workspace.settings or {}), "fx_rates": {**new, "updated_at": utcnow().isoformat(), "updated_by": g.user.name}}
    audit.record("workspace.fx_rates", entity_type="workspace", entity_id=g.workspace.id,
                 summary="Exchange rates: " + (", ".join(f"1 {c} = ₹{v:g}" for c, v in new.items()) or "cleared"), before=before, after=new)
    db.session.commit()
    return ok(svc.fx_meta())


# ---- the member's own page (no sign-in; the token in the link is the key) ------------------------------------------

def _by_token(token: str) -> FamilyMember:
    if not token or len(token) < 20:
        raise not_found("Page")
    with bypass_scope():
        m = db.session.query(FamilyMember).filter(FamilyMember.link_token == token, FamilyMember.deleted_at.is_(None)).one_or_none()
    if m is None:
        raise not_found("Page")
    set_tenant(m.workspace_id)
    g.workspace, g.user, g.permissions, g.features, g.member = db.session.get(Workspace, m.workspace_id), None, set(), set(), None
    return db.session.get(FamilyMember, m.id)


@link_bp.get("/<token>")
@limiter.limit("60 per minute")
def public_page(token):
    return ok(svc.public_view(_by_token(token)))


class PublicWalkthroughIn(Schema):
    starts_at: str = Field(min_length=10, max_length=40)
    timezone: str | None = Field(default=None, max_length=64)  # where they are right now, if not where we think
    note: str | None = Field(default=None, max_length=500)


@link_bp.post("/<token>/walkthrough")
@limiter.limit("10 per hour")
def public_walkthrough(token):
    m = _by_token(token)
    d = parse(PublicWalkthroughIn)
    tz = d.timezone if d.timezone and svc.valid_timezone(d.timezone) else m.timezone
    open_ = db.session.query(Walkthrough).filter(Walkthrough.member_id == m.id, Walkthrough.status == "requested").count()
    if open_ >= 3:
        raise conflict("You already have 3 requests waiting. We'll confirm them shortly.")
    svc.new_walkthrough(m, svc.parse_local(d.starts_at, tz), via="link", note=d.note, tz=tz)
    db.session.commit()
    return created(svc.public_view(m))
