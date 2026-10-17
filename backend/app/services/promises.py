"""Promise ledger: what reps promise buyers, who approved it, and the booking form that prints only approved promises.

A buyer shows up as a lead, then a client (contact) and a deal. A promise is stored against whichever record it was made
on, and every screen and the booking form look it up across the whole group, so a promise made while the buyer was still
a lead still prints on the booking form of their deal.
"""
from __future__ import annotations

import datetime as dt
import io
import uuid
from xml.sax.saxutils import escape

from flask import g
from sqlalchemy import or_

from app.core.errors import not_found
from app.core.permissions import has_permission
from app.extensions import db
from app.models import Contact, Deal, Lead, Project, Promise, Role, Tower, Unit, User, WorkspaceMember
from app.services import privacy

KINDS: dict[str, str] = {
    "discount": "Discount", "parking": "Parking", "fittings": "Fittings & furnishing", "possession": "Possession date",
    "payment_plan": "Payment plan", "waiver": "Charge waived", "other": "Other",
}
STATUSES: dict[str, str] = {"pending": "Waiting for approval", "approved": "Approved", "rejected": "Rejected", "cancelled": "Cancelled"}
SOURCES: dict[str, str] = {"manual": "Typed in", "whatsapp": "WhatsApp", "call": "Call notes", "visit": "Site visit notes", "note": "Notes", "chat": "AI assistant"}
_MODELS = {"lead": Lead, "contact": Contact, "deal": Deal}


def get_record(entity: str, ident) -> Lead | Contact | Deal:
    model = _MODELS.get(entity)
    if model is None:
        raise not_found("Record")
    row = db.session.query(model).filter(model.id == ident, model.workspace_id == g.workspace.id, model.deleted_at.is_(None)).one_or_none()
    if row is None:
        raise not_found(entity.capitalize())
    return row


def group(entity: str, ident) -> tuple[set, set, set]:
    """(lead ids, contact ids, deal ids) that are the same buyer as this record."""
    ws = g.workspace.id
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


def group_filter(entity: str, ident):
    leads, contacts, deals = group(entity, ident)
    conds = [col.in_(ids) for col, ids in ((Promise.lead_id, leads), (Promise.contact_id, contacts), (Promise.deal_id, deals)) if ids]
    return or_(*conds) if conds else Promise.id.is_(None)


def fill_links(data: dict) -> dict:
    """Fill in the rest of the buyer's records and the flat from whichever one the promise was made on."""
    deal = db.session.get(Deal, data["deal_id"]) if data.get("deal_id") else None
    lead = db.session.get(Lead, data["lead_id"]) if data.get("lead_id") else None
    if deal:
        data["lead_id"] = data.get("lead_id") or deal.lead_id
        data["contact_id"] = data.get("contact_id") or deal.contact_id
        lead = lead or (db.session.get(Lead, deal.lead_id) if deal.lead_id else None)
    if lead and lead.converted_contact_id:
        data["contact_id"] = data.get("contact_id") or lead.converted_contact_id
    if lead and lead.converted_deal_id:
        data["deal_id"] = data.get("deal_id") or lead.converted_deal_id
    if not data.get("unit_id"):
        data["unit_id"] = (deal.unit_id if deal else None) or (lead.unit_id if lead else None)
    if data.get("unit_id") and not data.get("project_id"):
        u = db.session.get(Unit, data["unit_id"])
        data["project_id"] = u.project_id if u else None
    if not data.get("project_id"):
        data["project_id"] = (deal.project_id if deal else None) or (lead.project_id if lead else None)
    return data


def buyer_name(p: Promise, names: dict) -> str | None:
    for key in (p.lead_id, p.contact_id, p.deal_id):
        if key and names.get(key):
            return names[key]
    return None


def serialize(rows: list[Promise]) -> list[dict]:
    if not rows:
        return []
    users = {r.id: r.name for r in db.session.query(User.id, User.name).filter(User.id.in_({u for p in rows for u in (p.promised_by, p.created_by, p.decided_by) if u}))}
    names: dict = {}
    lead_ids, contact_ids, deal_ids = ({getattr(p, f) for p in rows if getattr(p, f)} for f in ("lead_id", "contact_id", "deal_id"))
    if lead_ids:
        names |= {r.id: f"{r.first_name} {r.last_name or ''}".strip() for r in db.session.query(Lead.id, Lead.first_name, Lead.last_name).filter(Lead.id.in_(lead_ids))}
    if contact_ids:
        names |= {r.id: f"{r.first_name} {r.last_name or ''}".strip() for r in db.session.query(Contact.id, Contact.first_name, Contact.last_name).filter(Contact.id.in_(contact_ids))}
    if deal_ids:
        names |= dict(db.session.query(Deal.id, Deal.name).filter(Deal.id.in_(deal_ids)).all())
    units = {r.id: r for r in db.session.query(Unit.id, Unit.number, Tower.name.label("tower"), Project.name.label("project"))
             .join(Tower, Tower.id == Unit.tower_id).join(Project, Project.id == Unit.project_id)
             .filter(Unit.id.in_({p.unit_id for p in rows if p.unit_id}))} if any(p.unit_id for p in rows) else {}
    projects = dict(db.session.query(Project.id, Project.name).filter(Project.id.in_({p.project_id for p in rows if p.project_id})).all()) if any(p.project_id for p in rows) else {}
    out = []
    for p in rows:
        d = p.to_dict(exclude=("deleted_at",))
        u = units.get(p.unit_id)
        d.update({
            "kind_label": KINDS.get(p.kind, "Other"), "status_label": STATUSES.get(p.status, p.status), "source_label": SOURCES.get(p.source, p.source),
            "promised_by_name": users.get(p.promised_by), "created_by_name": users.get(p.created_by), "decided_by_name": users.get(p.decided_by),
            "buyer_name": buyer_name(p, names), "lead_name": names.get(p.lead_id), "deal_name": names.get(p.deal_id),
            "unit_label": f"{u.number} · {u.tower} · {u.project}" if u else None, "project_name": projects.get(p.project_id),
            "url": f"/app/deals/{p.deal_id}" if p.deal_id else f"/app/leads/{p.lead_id}" if p.lead_id else f"/app/contacts/{p.contact_id}" if p.contact_id else None,
        })
        out.append(d)
    return out


def approver_ids(workspace_id) -> list[uuid.UUID]:
    rows = (db.session.query(WorkspaceMember.user_id, Role.permissions).join(Role, Role.id == WorkspaceMember.role_id)
            .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.status == "active").all())
    return [uid for uid, perms in rows if has_permission(perms or [], "promises.approve")]


def can_approve() -> bool:
    return has_permission(getattr(g, "permissions", set()), "promises.approve")


# ---- booking form -----------------------------------------------------------------------------------------------------

def booking_form(entity: str, ident) -> tuple[bytes, str, int]:
    """PDF of the booking form with every approved promise. Returns (pdf, filename, approved count)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from app.services.comparison import _fonts

    rec = get_record(entity, ident)
    deal = rec if entity == "deal" else None
    lead = rec if entity == "lead" else (db.session.get(Lead, deal.lead_id) if deal and deal.lead_id else None)
    contact = rec if entity == "contact" else (db.session.get(Contact, deal.contact_id) if deal and deal.contact_id else None)
    if contact is None and lead is not None and lead.converted_contact_id:
        contact = db.session.get(Contact, lead.converted_contact_id)
    if deal is None and lead is not None and lead.converted_deal_id:
        deal = db.session.get(Deal, lead.converted_deal_id)
    person = contact or lead
    buyer = person.name if person else (deal.name if deal else "")
    phone = getattr(person, "phone", None)
    email = getattr(person, "email", None)
    unit = db.session.get(Unit, (deal.unit_id if deal else None) or (lead.unit_id if lead else None)) if ((deal and deal.unit_id) or (lead and lead.unit_id)) else None
    project = db.session.get(Project, unit.project_id) if unit else None
    if project is None and ((deal and deal.project_id) or (lead and lead.project_id)):
        project = db.session.get(Project, (deal.project_id if deal else None) or lead.project_id)
    tower = db.session.get(Tower, unit.tower_id) if unit else None
    price = (deal.value if deal and deal.value else None) or (unit.sale_price if unit else None)

    rows = (db.session.query(Promise).filter(Promise.workspace_id == g.workspace.id, Promise.deleted_at.is_(None), Promise.status == "approved",
                                             group_filter(entity, ident)).order_by(Promise.decided_at, Promise.created_at).all())
    data = serialize(rows)

    from app.services.ai.actions import money

    regular, bold = _fonts()
    ink, muted, brand, line = (colors.HexColor(c) for c in ("#0f172a", "#64748b", "#4f46e5", "#e2e8f0"))
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=18, leading=22, textColor=ink),
        "sub": ParagraphStyle("s", fontName=regular, fontSize=9.5, leading=13, textColor=muted),
        "h": ParagraphStyle("h", fontName=bold, fontSize=11.5, leading=15, textColor=brand, spaceBefore=6),
        "label": ParagraphStyle("l", fontName=regular, fontSize=9, leading=12, textColor=muted),
        "cell": ParagraphStyle("c", fontName=regular, fontSize=9.5, leading=13, textColor=ink),
        "cellb": ParagraphStyle("cb", fontName=bold, fontSize=9.5, leading=13, textColor=ink),
        "small": ParagraphStyle("sm", fontName=regular, fontSize=8, leading=10.5, textColor=muted),
        "th": ParagraphStyle("th", fontName=bold, fontSize=8.5, leading=11, textColor=colors.white),
    }
    blank = "_" * 32
    buf = io.BytesIO()
    margin = 36
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
                            title=f"Booking form · {buyer}", author=g.workspace.name)
    width = A4[0] - 2 * margin
    today = dt.date.today().strftime("%d %b %Y")
    e = lambda v: escape(str(v)) if v not in (None, "") else blank  # noqa: E731
    els = [Paragraph(escape(g.workspace.name), st["sub"]), Spacer(1, 2), Paragraph("Booking form", st["title"]), Spacer(1, 2),
           Paragraph(escape(f"Prepared on {today}" + (f" · RERA {project.rera_id}" if project and project.rera_id else "")), st["sub"]), Spacer(1, 12)]

    def kv(pairs):
        t = Table([[Paragraph(escape(k), st["label"]), Paragraph(v, st["cell"])] for k, v in pairs], colWidths=[120, width - 120])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, line), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        return t

    els += [Paragraph("Buyer", st["h"]), kv([("Name", e(buyer)), ("Phone", e(phone if privacy.can_view() else None)), ("Email", e(email)), ("Address", blank + blank)])]
    els += [Spacer(1, 6), Paragraph("Property", st["h"]), kv([
        ("Project", e(project.name if project else None)), ("Tower", e(tower.name if tower else None)),
        ("Flat", e(f"{unit.number}" + (f" · {unit.bhk}" if unit.bhk else "") + (f" · {float(unit.area_sqft):,.0f} sq ft" if unit.area_sqft else "") if unit else None)),
        ("Agreed price", e(money(price))),
    ])]
    els += [Spacer(1, 6), Paragraph("Promises approved by management", st["h"])]
    if data:
        head = [Paragraph(h, st["th"]) for h in ("#", "Promise", "Value", "Promised by", "Approved by")]
        body = [head]
        for i, p in enumerate(data, 1):
            what = f"<b>{escape(p['title'])}</b>" + (f"<br/><font size=8.5 color='#475569'>{escape(p['details'])}</font>" if p.get("details") else "")
            when = dt.date.fromisoformat(p["decided_at"][:10]).strftime("%d %b %Y") if p.get("decided_at") else ""
            body.append([Paragraph(str(i), st["cell"]), Paragraph(what, st["cell"]), Paragraph(escape(money(p["value"]) or "—"), st["cell"]),
                         Paragraph(escape(p.get("promised_by_name") or "—"), st["cell"]),
                         Paragraph(escape(p.get("decided_by_name") or "—") + f"<br/><font size=8 color='#64748b'>{when}</font>", st["cell"])])
        t = Table(body, colWidths=[22, width - 22 - 70 - 95 - 105, 70, 95, 105], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), brand), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]), ("LINEBELOW", (0, 0), (-1, -1), 0.5, line),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        els.append(t)
    else:
        els.append(Paragraph("No promises have been approved for this booking.", st["cell"]))
    els += [Spacer(1, 8), Paragraph(
        f"These are the only commitments {escape(g.workspace.name)} has made about this booking, beyond the price and the standard terms. "
        "Anything not written here, including anything said on calls, on WhatsApp or at the site, is not part of this booking unless it is added in writing "
        "and approved by management.", st["small"])]

    sign = Table([[Paragraph("<br/><br/>" + "_" * 26 + "<br/>" + label, st["label"]) for label in ("Buyer", "Sales executive", "Authorised signatory")]],
                 colWidths=[width / 3] * 3)
    sign.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 18)]))
    els += [Spacer(1, 10), KeepTogether([sign, Spacer(1, 6), Paragraph("Date: " + "_" * 20 + "    Place: " + "_" * 26, st["label"])])]
    doc.build(els)
    safe = "".join(c for c in buyer if c.isalnum() or c in " -")[:60].strip() or "buyer"
    return buf.getvalue(), f"Booking form - {safe}.pdf", len(data)
