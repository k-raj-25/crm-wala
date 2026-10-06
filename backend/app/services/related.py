from __future__ import annotations

from app.extensions import db
from app.models import Company, Contact, Deal, Lead


def attach_related(objs: list, dicts: list[dict]) -> None:
    """Add `related` = {type, id, label} to serialized records that link to a lead/contact/company/deal."""
    ids = {k: {getattr(o, f"{k}_id") for o in objs if getattr(o, f"{k}_id", None)} for k in ("lead", "contact", "company", "deal")}
    labels: dict[tuple[str, object], str] = {}
    if ids["lead"]:
        for r in db.session.query(Lead.id, Lead.first_name, Lead.last_name).filter(Lead.id.in_(ids["lead"])):
            labels[("lead", r.id)] = f"{r.first_name} {r.last_name or ''}".strip()
    if ids["contact"]:
        for r in db.session.query(Contact.id, Contact.first_name, Contact.last_name).filter(Contact.id.in_(ids["contact"])):
            labels[("contact", r.id)] = f"{r.first_name} {r.last_name or ''}".strip()
    if ids["company"]:
        for r in db.session.query(Company.id, Company.name).filter(Company.id.in_(ids["company"])):
            labels[("company", r.id)] = r.name
    if ids["deal"]:
        for r in db.session.query(Deal.id, Deal.name).filter(Deal.id.in_(ids["deal"])):
            labels[("deal", r.id)] = r.name
    for o, d in zip(objs, dicts):
        d["related"] = []
        for k in ("deal", "contact", "company", "lead"):
            rid = getattr(o, f"{k}_id", None)
            if rid and (k, rid) in labels:
                d["related"].append({"type": k, "id": str(rid), "label": labels[(k, rid)]})
