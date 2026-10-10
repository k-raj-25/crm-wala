"""Real-estate projects and their towers. The building view payload lives here too."""
from __future__ import annotations

from flask import Blueprint, g
from sqlalchemy import func, literal_column

from app.core.auth import protect, require
from app.core.crud import CrudResource
from app.core.errors import conflict, not_found
from app.core.responses import created, no_content, ok
from app.extensions import db
from app.models import Project, Tower, Unit
from app.models.base import utcnow
from app.schemas.common import parse, provided
from app.schemas.realestate import AddFloorsIn, ProjectIn, ProjectPatch, TowerIn, TowerPatch
from app.services import activities, audit, inventory

bp = Blueprint("projects", __name__, url_prefix="/api/v1/projects")

SEARCH = literal_column("(coalesce(projects.name,'') || ' ' || coalesce(projects.developer,'') || ' ' || coalesce(projects.city,'') || ' ' || coalesce(projects.locality,'') || ' ' || coalesce(projects.sector,''))")


class ProjectResource(CrudResource):
    name, entity_type, model = "projects", "project", Project
    create_schema, patch_schema = ProjectIn, ProjectPatch
    search_cols = [SEARCH]
    sort_fields = {"created_at": Project.created_at, "updated_at": Project.updated_at, "name": Project.name, "city": Project.city}
    default_sort = "name"
    filters = {"city": ("in", Project.city), "kind": ("in", Project.kind), "stage": ("in", Project.stage), "owner_id": ("in", Project.owner_id), "tags": ("array", Project.tags)}
    refs = {"owner_id": "member"}
    export_columns = [("Name", lambda o: o.name), ("Developer", lambda o: o.developer), ("City", lambda o: o.city), ("Locality", lambda o: o.locality),
                      ("Sector", lambda o: o.sector), ("RERA", lambda o: o.rera_id), ("Created", lambda o: o.created_at.isoformat())]

    def serialize_many(self, objs):
        out = super().serialize_many(objs)
        if not objs:
            return out
        inventory.release_expired_holds(g.workspace.id)
        pids = [o.id for o in objs]
        by_project = inventory.counts_by(Unit.project_id, pids)
        tower_ids = [t.id for o in objs for t in o.towers]
        by_tower = inventory.counts_by(Unit.tower_id, tower_ids)
        prices = dict(db.session.query(Unit.project_id, func.min(Unit.sale_price)).filter(
            Unit.project_id.in_(pids), Unit.deleted_at.is_(None), Unit.status.in_(inventory.AVAILABLE), Unit.sale_price.isnot(None)).group_by(Unit.project_id).all())
        for d, o in zip(out, objs):
            d["summary"] = inventory.summarize(by_project[o.id])
            d["starting_price"] = inventory.money(prices.get(o.id))
            d["towers"] = [{**t.to_dict(exclude=("workspace_id",)), "summary": inventory.summarize(by_tower[t.id])} for t in o.towers]
        return out

    def after_create(self, p, data):
        activities.log_activity("created", f"Project created: {p.name}", touch=False)

    def prepare_create(self, data):
        data["owner_id"] = data.get("owner_id") or g.user.id
        return data

    def after_delete(self, p):
        db.session.query(Unit).filter(Unit.project_id == p.id, Unit.deleted_at.is_(None)).update({"deleted_at": utcnow()}, synchronize_session=False)


res = ProjectResource()
res.register(bp)


# ---- towers ----------------------------------------------------------------------------------------------------------

def _tower(project_id, tower_id) -> Tower:
    t = db.session.query(Tower).filter(Tower.id == tower_id, Tower.project_id == project_id, Tower.workspace_id == g.workspace.id).one_or_none()
    if t is None:
        raise not_found("Tower")
    return t


@bp.post("/<uuid:pid>/towers")
@protect("projects.update")
def create_tower(pid):
    project = res.get_or_404(pid)
    require("units.create")
    d = parse(TowerIn)
    if db.session.query(Tower.id).filter_by(project_id=project.id, name=d.name).first():
        raise conflict("This project already has a tower with that name")
    t = Tower(workspace_id=g.workspace.id, project_id=project.id, name=d.name, floors=d.floors, has_ground=d.has_ground,
              position=db.session.query(func.count(Tower.id)).filter_by(project_id=project.id).scalar())
    db.session.add(t)
    db.session.flush()
    n = inventory.generate_tower(t, d.units_per_floor, kind=d.kind, bhk=d.bhk, area=d.area_sqft, sale_price=d.sale_price, monthly_rent=d.monthly_rent, status=d.status)
    audit.record("tower.created", entity_type="project", entity_id=project.id, summary=f"Added {t.name} ({n} units) to {project.name}")
    db.session.commit()
    return created({**t.to_dict(), "units_created": n})


@bp.patch("/<uuid:pid>/towers/<uuid:tid>")
@protect("projects.update")
def update_tower(pid, tid):
    t = _tower(pid, tid)
    ch = provided(parse(TowerPatch))
    if "name" in ch and ch["name"] != t.name and db.session.query(Tower.id).filter_by(project_id=pid, name=ch["name"]).first():
        raise conflict("This project already has a tower with that name")
    for k, v in ch.items():
        if v is not None:
            setattr(t, k, v)
    db.session.commit()
    return ok(t.to_dict())


@bp.delete("/<uuid:pid>/towers/<uuid:tid>")
@protect("projects.delete")
def delete_tower(pid, tid):
    t = _tower(pid, tid)
    db.session.query(Unit).filter(Unit.tower_id == t.id).update({"deleted_at": utcnow()}, synchronize_session=False)
    db.session.delete(t)
    audit.record("tower.deleted", entity_type="project", entity_id=pid, summary=f"Deleted tower {t.name}")
    db.session.commit()
    return no_content()


@bp.post("/<uuid:pid>/towers/<uuid:tid>/floors")
@protect("projects.update")
def add_floors(pid, tid):
    """Build more floors on top. Each new floor copies the defaults of the current top floor."""
    t = _tower(pid, tid)
    require("units.create")
    d = parse(AddFloorsIn)
    top = db.session.query(Unit).filter(Unit.tower_id == t.id, Unit.deleted_at.is_(None), Unit.floor == t.floors).first()
    base = dict(kind=top.kind, bhk=top.bhk, area=top.area_sqft, sale_price=top.sale_price, monthly_rent=top.monthly_rent) if top else {}
    created_n = 0
    for _ in range(d.count):
        t.floors += 1
        created_n += len(inventory.add_floor_units(t, t.floors, d.units_per_floor, **base))
    db.session.commit()
    return ok({"floors": t.floors, "units_created": created_n})


@bp.get("/<uuid:pid>/towers/<uuid:tid>/building")
@protect("projects.read")
def building(pid, tid):
    """Everything the building view needs in one request: floors (top first) with their units, plus summary figures."""
    project = res.get_or_404(pid)
    t = _tower(pid, tid)
    require("units.read")
    if inventory.release_expired_holds(g.workspace.id):
        db.session.commit()
    units = db.session.query(Unit).filter(Unit.tower_id == t.id, Unit.deleted_at.is_(None)).order_by(Unit.floor.desc(), Unit.position, Unit.number).all()
    counts: dict[str, int] = {}
    floors: dict[int, list[dict]] = {}
    for u in units:
        counts[u.status] = counts.get(u.status, 0) + 1
        floors.setdefault(u.floor, []).append({
            "id": str(u.id), "number": u.number, "floor": u.floor, "position": u.position, "status": u.status, "kind": u.kind, "bhk": u.bhk,
            "area_sqft": inventory.money(u.area_sqft), "facing": u.facing, "sale_price": inventory.money(u.sale_price), "monthly_rent": inventory.money(u.monthly_rent),
            "hold_until": u.hold_until.isoformat() if u.hold_until else None,
        })
    for f in range(t.floors, -1 if t.has_ground else 0, -1):  # keep empty floors visible so a tower never looks shorter than it is
        floors.setdefault(f, [])
    stock = db.session.query(func.coalesce(func.sum(Unit.sale_price), 0)).filter(Unit.tower_id == t.id, Unit.deleted_at.is_(None), Unit.status == "for_sale").scalar()
    return ok({
        "project": {"id": str(project.id), "name": project.name, "city": project.city, "locality": project.locality, "sector": project.sector,
                    "developer": project.developer, "stage": project.stage},
        "tower": t.to_dict(),
        "floors": [{"floor": f, "units": floors[f]} for f in sorted(floors, reverse=True)],
        "summary": {**inventory.summarize(counts), "for_sale_value": float(stock or 0), "units_per_floor": max((len(v) for v in floors.values()), default=0), "floors": len(floors)},
        "statuses": inventory.STATUSES,
    })


@bp.get("/<uuid:pid>/units-summary")
@protect("projects.read")
def units_summary(pid):
    """Analytics tab: stock by status, by BHK, and by tower."""
    res.get_or_404(pid)
    rows = db.session.query(Unit.bhk, Unit.status, func.count()).filter(Unit.project_id == pid, Unit.deleted_at.is_(None)).group_by(Unit.bhk, Unit.status).all()
    by_bhk: dict[str, dict[str, int]] = {}
    for bhk, st, n in rows:
        by_bhk.setdefault(bhk or "Other", {})[st] = n
    avg = db.session.query(func.avg(Unit.sale_price / func.nullif(Unit.area_sqft, 0))).filter(Unit.project_id == pid, Unit.deleted_at.is_(None), Unit.sale_price.isnot(None)).scalar()
    sold_value = db.session.query(func.coalesce(func.sum(Unit.sale_price), 0)).filter(Unit.project_id == pid, Unit.deleted_at.is_(None), Unit.status == "sold").scalar()
    return ok({"by_bhk": by_bhk, "avg_price_per_sqft": float(avg) if avg is not None else None, "sold_value": float(sold_value or 0)})

