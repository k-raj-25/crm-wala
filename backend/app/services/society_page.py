"""The public society page: a no-login web page with everything about one project (photos, layouts, floor plans, brochure,
amenities, RERA) that an employee sends to a client as a link.

The link is a signed token, so nobody can guess another society's page. It carries the project, the employee who shared
it (their name goes on the page as the contact), and optionally the lead / client it was sent to, so the employee hears
when that client opens it. Nothing is stored per link: a deleted project, or a workspace that is no longer active, just
stops its links working."""
from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from dataclasses import dataclass

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models import Contact, FileAsset, Lead, Project, Tower, Unit, User, Workspace, WorkspaceMember
from app.services import inventory
from app.services.comparison import STAGES, _indian_digits, inr
from app.services.society_comparison import PROJECT_KINDS, _key

_SIG = 12  # bytes of HMAC kept in the token; 96 bits is plenty for an unguessable link
_LEAD, _CONTACT = 1, 2
HIDE_PRICES = 1  # flag bit: the employee chose not to show prices on this link
PUBLIC_KINDS = ("brochure", "photo", "floor_plan")


@dataclass(frozen=True)
class Link:
    project_id: uuid.UUID
    sharer_id: uuid.UUID
    flags: int = 0
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None

    @property
    def hide_prices(self) -> bool:
        return bool(self.flags & HIDE_PRICES)


def _mac(body: bytes) -> bytes:
    return hmac.new(current_app.config["SECRET_KEY"].encode(), b"society-page|" + body, hashlib.sha256).digest()[:_SIG]


def make_token(link: Link) -> str:
    """project (16) + sharer (16) + flags (1) + [kind (1) + lead / contact (16)] + signature (12), base64url without padding."""
    body = link.project_id.bytes + link.sharer_id.bytes + bytes([link.flags])
    if link.lead_id:
        body += bytes([_LEAD]) + link.lead_id.bytes
    elif link.contact_id:
        body += bytes([_CONTACT]) + link.contact_id.bytes
    return base64.urlsafe_b64encode(body + _mac(body)).decode().rstrip("=")


def read_token(token: str) -> Link | None:
    """The link inside a token, or None for anything tampered with or malformed."""
    if not token or len(token) > 120:
        return None
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except (ValueError, TypeError):
        return None
    if len(raw) not in (33 + _SIG, 50 + _SIG):
        return None
    body, sig = raw[:-_SIG], raw[-_SIG:]
    if not hmac.compare_digest(_mac(body), sig):
        return None
    rel = {}
    if len(body) == 50:
        kind, rid = body[33], uuid.UUID(bytes=body[34:50])
        if kind not in (_LEAD, _CONTACT):
            return None
        rel = {"lead_id": rid} if kind == _LEAD else {"contact_id": rid}
    return Link(project_id=uuid.UUID(bytes=body[:16]), sharer_id=uuid.UUID(bytes=body[16:32]), flags=body[32], **rel)


def page_url(token: str) -> str:
    return f"{current_app.config['WEB_ORIGIN']}/s/{token}"


def file_url(token: str, fid, *, download: bool = False) -> str:
    return f"{current_app.config['WEB_ORIGIN']}/api/v1/public/societies/{token}/files/{fid}" + ("?download=1" if download else "")


def recipient(link: Link):
    """The lead or client this link was sent to, if it still exists in the project's workspace."""
    if link.lead_id:
        return db.session.query(Lead).filter(Lead.id == link.lead_id, Lead.deleted_at.is_(None)).one_or_none()
    if link.contact_id:
        return db.session.query(Contact).filter(Contact.id == link.contact_id, Contact.deleted_at.is_(None)).one_or_none()
    return None


def _contact_person(project: Project, link: Link) -> dict | None:
    """The employee who shared the link, by name only: the page carries no phone numbers, so clients reply through the
    chat or email the link came in."""
    row = db.session.query(User.name, User.avatar_url).join(WorkspaceMember, WorkspaceMember.user_id == User.id).filter(
        WorkspaceMember.workspace_id == project.workspace_id, WorkspaceMember.user_id == link.sharer_id, WorkspaceMember.status == "active").first()
    return {"name": row[0], "avatar_url": row[1]} if row else None


def build(project: Project, link: Link, token: str) -> dict:
    """Everything the public page shows. Only public-safe fields: no owner, tags, buyers or flat-level details."""
    pid = project.id
    show_prices = not link.hide_prices
    counts = inventory.summarize(inventory.counts_by(Unit.project_id, [pid]).get(pid, {}))
    towers = db.session.query(func.count(Tower.id)).filter(Tower.project_id == pid).scalar() or 0
    live = (Unit.project_id == pid, Unit.deleted_at.is_(None), Unit.status.in_(inventory.AVAILABLE))
    lo, hi, rate = db.session.query(func.min(Unit.sale_price), func.max(Unit.sale_price), func.avg(Unit.sale_price / func.nullif(Unit.area_sqft, 0))).filter(
        *live, Unit.sale_price.isnot(None)).one()
    by_size: dict[str, list] = {}
    for bhk, n, cheapest in db.session.query(Unit.bhk, func.count(), func.min(Unit.sale_price)).filter(*live).group_by(Unit.bhk).all():
        cur = by_size.setdefault(_key(bhk), [0, None])
        cur[0] += n
        if cheapest is not None and (cur[1] is None or cheapest < cur[1]):
            cur[1] = cheapest

    files = db.session.query(FileAsset).filter(FileAsset.project_id == pid, FileAsset.unit_id.is_(None), FileAsset.deleted_at.is_(None),
                                               FileAsset.doc_kind.in_(PUBLIC_KINDS)).order_by(FileAsset.created_at).all()
    by_id = {f.id: f for f in files}

    def shown(f: FileAsset | None) -> dict | None:
        if f is None:
            return None
        return {"id": str(f.id), "filename": f.filename, "mime_type": f.mime_type, "size_bytes": f.size_bytes,
                "url": file_url(token, f.id), "download_url": file_url(token, f.id, download=True)}

    sizes = []
    for z in project.sizes or []:
        if not z.get("label"):
            continue
        n, cheapest = by_size.get(_key(z["label"]), (0, None))
        plan = None
        if z.get("floor_plan_file_id"):
            try:
                plan = by_id.get(uuid.UUID(z["floor_plan_file_id"]))
            except ValueError:
                plan = None
        sizes.append({"label": z["label"], "area_sqft": z.get("area_sqft"),
                      "area": f"{_indian_digits(round(z['area_sqft']))} sq ft" if z.get("area_sqft") else None,
                      "from_price": inr(cheapest) if show_prices and cheapest is not None else None, "available": n,
                      "floor_plan": shown(plan) if plan is not None and plan.doc_kind == "floor_plan" else None})

    brochures = [f for f in files if f.doc_kind == "brochure"]
    photos = [f for f in files if f.doc_kind == "photo"][: inventory.MAX_PROJECT_PHOTOS]
    ws = db.session.get(Workspace, project.workspace_id)
    return {
        "society": {
            "name": project.name, "developer": project.developer, "kind": PROJECT_KINDS.get(project.kind, project.kind),
            "stage": STAGES.get(project.stage, project.stage), "stage_key": project.stage,
            "possession": f"{project.possession_date:%b %Y}" if project.possession_date else None,
            "location": ", ".join(x for x in (project.sector, project.locality, project.city) if x) or None,
            "city": project.city, "address": project.address, "rera_id": project.rera_id, "description": project.description,
            "amenities": [a for a in (project.amenities or []) if a and a.strip()], "video_url": project.video_url,
            "towers": towers, "total_flats": counts["total"], "available": counts["available"],
            "starting_price": inr(lo) if show_prices and lo is not None else None,
            "price_range": (inr(lo) if lo == hi else f"{inr(lo)} – {inr(hi)}") if show_prices and lo is not None else None,
            "avg_rate": f"₹{_indian_digits(round(rate))}" if show_prices and rate is not None else None,
        },
        "sizes": sizes,
        "photos": [shown(f) for f in photos],
        "brochure": shown(brochures[-1]) if brochures else None,
        "floor_plans": [s["floor_plan"] for s in sizes if s["floor_plan"]],
        "contact": _contact_person(project, link),
        "company": {"name": ws.name, "logo_url": ws.logo_url, "website": ws.website} if ws else None,
        "shared_with": _first_name(recipient(link)),
    }


def _first_name(rec) -> str | None:
    return (getattr(rec, "first_name", None) or "").strip() or None
