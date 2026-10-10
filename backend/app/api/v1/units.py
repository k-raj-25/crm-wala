"""Units (flats, shops, villas, plots): CRUD, one-tap status changes with holds, history, and matching buyers."""
from __future__ import annotations

from flask import Blueprint, g
from sqlalchemy import func, literal_column

from app.core.auth import protect
from app.core.crud import CrudResource
from app.core.errors import conflict, not_found
from app.core.responses import ok
from app.extensions import db
from app.models import Contact, Lead, Project, Tower, Unit, UnitEvent
from app.models.base import utcnow
from app.schemas.common import parse
from app.schemas.realestate import StatusIn, UnitIn, UnitPatchIn
from app.services import audit, inventory

bp = Blueprint("units", __name__, url_prefix="/api/v1/units")

SEARCH = literal_column("(coalesce(units.number,'') || ' ' || coalesce(units.bhk,''))")


class UnitResource(CrudResource):
    name, entity_type, model = "units", "unit", Unit
    create_schema, patch_schema = UnitIn, UnitPatchIn
    owner_field = None
    search_cols = [SEARCH]
    sort_fields = {"created_at": Unit.created_at, "number": Unit.number, "floor": Unit.floor, "sale_price": Unit.sale_price,
                   "monthly_rent": Unit.monthly_rent, "area_sqft": Unit.area_sqft, "status": Unit.status, "status_changed_at": Unit.status_changed_at}
    default_sort = "floor,number"
    filters = {
        "project_id": ("in", Unit.project_id), "tower_id": ("in", Unit.tower_id), "status": ("in", Unit.status), "bhk": ("in", Unit.bhk),
        "kind": ("in", Unit.kind), "floor": ("in", Unit.floor), "facing": ("in", Unit.facing), "sale_price": ("num", Unit.sale_price),
        "monthly_rent": ("num", Unit.monthly_rent), "area_sqft": ("num", Unit.area_sqft), "owner_contact_id": ("in", Unit.owner_contact_id),
        "tags": ("array", Unit.tags),
    }
    refs = {"owner_contact_id": Contact}
    bulk_fields = {"status"}
    export_columns = [("Unit", lambda o: o.number), ("Floor", lambda o: o.floor), ("Type", lambda o: o.kind), ("BHK", lambda o: o.bhk),
                      ("Area (sqft)", lambda o: o.area_sqft), ("Facing", lambda o: o.facing), ("Status", lambda o: o.status),
                      ("Sale price", lambda o: o.sale_price), ("Monthly rent", lambda o: o.monthly_rent)]

    def label(self, o):
        return o.name

    def serialize_many(self, objs):
        out = super().serialize_many(objs)
        if not objs:
            return out
        tower_ids, project_ids = {o.tower_id for o in objs}, {o.project_id for o in objs}
        towers = dict(db.session.query(Tower.id, Tower.name).filter(Tower.id.in_(tower_ids)).all())
        projects = {r.id: r for r in db.session.query(Project.id, Project.name, Project.city, Project.locality).filter(Project.id.in_(project_ids)).all()}
        contacts = inventory.people({c for o in objs for c in (o.owner_contact_id, o.occupant_contact_id)})
        leads = {r.id: f"{r.first_name} {r.last_name or ''}".strip() for r in db.session.query(Lead.id, Lead.first_name, Lead.last_name).filter(
            Lead.id.in_({o.hold_lead_id for o in objs if o.hold_lead_id})).all()} if any(o.hold_lead_id for o in objs) else {}
        users = inventory.user_names({o.held_by for o in objs})
        now = utcnow()
        for d, o in zip(out, objs):
            d["name"] = o.name
            d["tower_name"], p = towers.get(o.tower_id), projects.get(o.project_id)
            d["project_name"], d["project_city"] = (p.name, p.city) if p else (None, None)
            d["floor_label"] = inventory.floor_label(o.floor)
            d["owner_contact"], d["occupant_contact"] = contacts.get(o.owner_contact_id), contacts.get(o.occupant_contact_id)
            d["hold_lead"] = {"id": str(o.hold_lead_id), "name": leads.get(o.hold_lead_id)} if o.hold_lead_id else None
            d["held_by_name"] = users.get(o.held_by)
            d["days_in_status"] = (now - o.status_changed_at).days if o.status_changed_at else None
            m = getattr(o, "_match", None)
            if m:
                d["match"] = m
        return out

    def list(self):
        if inventory.release_expired_holds(g.workspace.id):
            db.session.commit()
        return super().list()

    def _tower_of(self, tower_id) -> Tower:
        t = db.session.query(Tower).filter(Tower.id == tower_id, Tower.workspace_id == g.workspace.id).one_or_none()
        if t is None:
            raise not_found("Tower")
        return t

    def _unique(self, tower_id, number, exclude=None):
        q = db.session.query(Unit.id).filter(Unit.tower_id == tower_id, Unit.number == number, Unit.deleted_at.is_(None))
        if exclude:
            q = q.filter(Unit.id != exclude)
        if q.first():
            raise conflict(f"Unit {number} already exists in this tower")

    def prepare_create(self, data):
        t = self._tower_of(data["tower_id"])
        self._unique(t.id, data["number"])
        data["project_id"] = t.project_id
        data["position"] = (db.session.query(func.coalesce(func.max(Unit.position), 0)).filter(Unit.tower_id == t.id, Unit.floor == data["floor"]).scalar() or 0) + 1
        data["status_changed_at"] = utcnow()
        g.unit_status = data.pop("status", "vacant")  # applied after insert so holds/history stay consistent
        return data

    def after_create(self, u, data):
        inventory.log_event(u, "created", to_status="vacant")
        st = g.pop("unit_status", "vacant")
        if st != "vacant":
            inventory.apply_status(u, st, note="Created")

    def prepare_update(self, unit, changes):
        if "number" in changes and changes["number"] != unit.number:
            self._unique(unit.tower_id, changes["number"], unit.id)
        g.unit_status = changes.pop("status", None)
        return changes

    def after_update(self, unit, before, changes):
        st = g.pop("unit_status", None)
        if st and st != unit.status:
            inventory.apply_status(unit, st)


unit_res = UnitResource()
unit_res.register(bp)


@bp.post("/<uuid:ident>/status")
@protect("units.update")
def set_status(ident):
    u = unit_res.get_or_404(ident)
    d = parse(StatusIn)
    before = u.status
    if d.contact_id and not db.session.query(Contact.id).filter(Contact.id == d.contact_id, Contact.workspace_id == g.workspace.id).first():
        raise not_found("Contact")
    if d.lead_id and not db.session.query(Lead.id).filter(Lead.id == d.lead_id, Lead.workspace_id == g.workspace.id).first():
        raise not_found("Lead")
    inventory.apply_status(u, d.status, note=d.note, lead_id=d.lead_id, contact_id=d.contact_id, hold_hours=d.hold_hours)
    audit.record("unit.status_changed", entity_type="unit", entity_id=u.id, summary=f"{u.name}: {before} → {u.status}", before={"status": before}, after={"status": u.status})
    db.session.commit()
    return ok(unit_res.serialize(u))


@bp.get("/<uuid:ident>/history")
@protect("units.read")
def history(ident):
    u = unit_res.get_or_404(ident)
    rows = db.session.query(UnitEvent).filter(UnitEvent.unit_id == u.id).order_by(UnitEvent.created_at.desc()).limit(50).all()
    names = inventory.user_names({r.user_id for r in rows})
    return ok([{**r.to_dict(), "user_name": names.get(r.user_id)} for r in rows])


@bp.get("/<uuid:ident>/matches")
@protect("units.read")
def matches(ident):
    """Open leads whose requirement fits this unit (intent, BHK, budget)."""
    u = unit_res.get_or_404(ident)
    return ok(inventory.matching_leads(u))


@bp.get("/meta")
@protect("units.read")
def meta():
    return ok({"statuses": inventory.STATUSES, "available": list(inventory.AVAILABLE)})
