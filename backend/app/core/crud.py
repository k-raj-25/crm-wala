"""Generic, tenant-scoped CRUD resource: list/filter/sort/paginate/search, create, read, patch, soft delete,
bulk actions and CSV export. Entity modules subclass it and override small hooks.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import uuid
from typing import Any, Callable, ClassVar

from flask import Blueprint, Response, g, request
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY

from app.core.auth import protect, require
from app.core.errors import ApiError, bad_request, not_found
from app.core.responses import created, no_content, ok
from app.extensions import db
from app.models import User, WorkspaceMember
from app.schemas.common import parse, provided
from app.services import analytics, audit
from app.services import custom_fields as cf_service
from app.services.usage import check_limit

MAX_PER_PAGE = 100


def csv_list(name: str) -> list[str]:
    raw = request.args.get(name, "")
    return [v for v in (s.strip() for s in raw.split(",")) if v]


def parse_date(v: str | None, end: bool = False) -> dt.datetime | None:
    if not v:
        return None
    try:
        d = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise bad_request(f"Invalid date: {v}", "invalid_date")
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    if end and len(v) <= 10:
        d = d + dt.timedelta(days=1) - dt.timedelta(microseconds=1)
    return d


def users_map(ids: set) -> dict[uuid.UUID, dict]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = db.session.query(User.id, User.name, User.avatar_url, User.email).filter(User.id.in_(ids)).all()
    return {r.id: {"id": str(r.id), "name": r.name, "avatar_url": r.avatar_url, "email": r.email} for r in rows}


def ensure_member(user_id) -> None:
    if user_id is None:
        return
    ok_ = db.session.query(WorkspaceMember.id).filter_by(workspace_id=g.workspace.id, user_id=user_id, status="active").first()
    if not ok_:
        raise ApiError(422, "validation_error", "That person isn't a member of this workspace", {"owner_id": "Not a workspace member"})


def ensure_ref(model, ident, field: str) -> None:
    """Referential check scoped to the current tenant (FK checks themselves bypass RLS)."""
    if ident is None:
        return
    if not db.session.query(model.id).filter(model.id == ident, model.workspace_id == g.workspace.id).first():
        raise ApiError(422, "validation_error", "Referenced record not found", {field: "Not found"})


class CrudResource:
    name: ClassVar[str]  # url segment + permission prefix
    entity_type: ClassVar[str]  # lead|contact|company|deal|task
    model: ClassVar[type]
    create_schema: ClassVar[type]
    patch_schema: ClassVar[type]
    search_cols: ClassVar[list] = []
    sort_fields: ClassVar[dict[str, Any]] = {}
    default_sort: ClassVar[str] = "-created_at"
    filters: ClassVar[dict[str, tuple]] = {}  # param -> ("eq"|"in"|"array"|"bool"|"date"|"num", column)
    refs: ClassVar[dict[str, Any]] = {}  # fk field -> model | "member"
    soft_delete: ClassVar[bool] = True
    limit_key: ClassVar[str | None] = None
    custom_fields: ClassVar[bool] = False
    bulk_fields: ClassVar[set[str]] = set()
    export_columns: ClassVar[list[tuple[str, Callable[[Any], Any]]]] = []
    owner_field: ClassVar[str | None] = "owner_id"

    # ---- hooks -------------------------------------------------------------------------
    def base_query(self):
        q = select(self.model).where(self.model.workspace_id == g.workspace.id)
        if self.soft_delete:
            q = q.where(self.model.deleted_at.is_(None))
        return q

    def extra_filters(self, q):
        return q

    def serialize_many(self, objs: list) -> list[dict]:
        users = users_map({getattr(o, self.owner_field) for o in objs} if self.owner_field else set())
        out = []
        for o in objs:
            d = o.to_dict()
            if self.owner_field:
                d["owner"] = users.get(getattr(o, self.owner_field))
            out.append(d)
        return out

    def serialize(self, obj) -> dict:
        return self.serialize_many([obj])[0]

    def prepare_create(self, data: dict) -> dict:
        return data

    def after_create(self, obj, data: dict) -> None: ...

    def prepare_update(self, obj, changes: dict) -> dict:
        return changes

    def after_update(self, obj, before: dict, changes: dict) -> None: ...

    def before_delete(self, obj) -> None: ...

    def after_delete(self, obj) -> None: ...

    def label(self, obj) -> str:
        return getattr(obj, "name", None) or getattr(obj, "title", None) or str(obj.id)

    # ---- query building ----------------------------------------------------------------
    def apply_search(self, q):
        term = request.args.get("q", "").strip()
        if term and self.search_cols:
            like = f"%{term.replace('%', '').replace('_', ' ')}%"
            q = q.where(or_(*[c.ilike(like) for c in self.search_cols]))
        return q

    def apply_filters(self, q):
        m = self.model
        for param, spec in self.filters.items():
            kind, col = spec[0], spec[1]
            if kind == "eq":
                v = request.args.get(param)
                if v:
                    q = q.where(col == (g.user.id if v == "me" and param.endswith("_id") else v))
            elif kind == "in":
                vals = csv_list(param)
                if vals:
                    if param.endswith("_id") and "me" in vals:
                        vals = [str(g.user.id) if v == "me" else v for v in vals]
                    if "none" in vals and param.endswith("_id"):
                        vals = [v for v in vals if v != "none"]
                        q = q.where(or_(col.in_(vals) if vals else False, col.is_(None)))
                    else:
                        q = q.where(col.in_(vals))
            elif kind == "array":
                vals = csv_list(param)
                if vals:
                    q = q.where(col.overlap(cast(vals, PG_ARRAY(String))))
            elif kind == "bool":
                v = request.args.get(param)
                if v in ("true", "false"):
                    q = q.where(col.is_(v == "true"))
            elif kind == "date":
                lo, hi = parse_date(request.args.get(f"{param}_from")), parse_date(request.args.get(f"{param}_to"), end=True)
                if lo:
                    q = q.where(col >= lo)
                if hi:
                    q = q.where(col <= hi)
            elif kind == "num":
                for suffix, op in (("_min", lambda c, v: c >= v), ("_max", lambda c, v: c <= v)):
                    v = request.args.get(param + suffix)
                    if v not in (None, ""):
                        try:
                            q = q.where(op(col, float(v)))
                        except ValueError:
                            raise bad_request(f"Invalid number for {param}{suffix}")
        return self.extra_filters(q)

    def apply_sort(self, q, sort: str | None = None):
        spec = sort or request.args.get("sort") or self.default_sort
        clauses = []
        for part in [p for p in spec.split(",") if p]:
            desc = part.startswith("-")
            key = part.lstrip("-+")
            col = self.sort_fields.get(key)
            if col is None:
                continue
            clauses.append(col.desc().nulls_last() if desc else col.asc().nulls_last())
        if not clauses:
            clauses.append(self.sort_fields.get("created_at", self.model.created_at).desc())
        return q.order_by(*clauses, self.model.id)

    def paginate(self, q):
        try:
            page = max(int(request.args.get("page", 1)), 1)
            per = min(max(int(request.args.get("per_page", 25)), 1), MAX_PER_PAGE)
        except ValueError:
            raise bad_request("page and per_page must be numbers")
        total = db.session.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
        rows = db.session.scalars(q.limit(per).offset((page - 1) * per)).unique().all()
        return rows, {"page": page, "per_page": per, "total": total, "pages": max((total + per - 1) // per, 1)}

    def get_or_404(self, ident):
        obj = db.session.scalars(self.base_query().where(self.model.id == ident)).unique().one_or_none()
        if obj is None:
            raise not_found(self.entity_type.capitalize())
        return obj

    def validate_refs(self, data: dict) -> None:
        for field, target in self.refs.items():
            if field in data:
                if target == "member":
                    ensure_member(data[field])
                else:
                    ensure_ref(target, data[field], field)

    # ---- handlers ----------------------------------------------------------------------
    def list(self):
        q = self.apply_sort(self.apply_filters(self.apply_search(self.base_query())))
        rows, meta = self.paginate(q)
        return ok(self.serialize_many(list(rows)), meta)

    def create(self):
        model = parse(self.create_schema)
        data = model.model_dump(exclude_unset=False)
        if self.limit_key:
            check_limit(g.workspace, self.limit_key)
        data = self.prepare_create(data)
        self.validate_refs(data)
        if self.custom_fields:
            data["custom"] = cf_service.validate(g.workspace.id, self.entity_type, data.get("custom"))
        obj = self.model(workspace_id=g.workspace.id, **data)
        db.session.add(obj)
        db.session.flush()
        self.after_create(obj, data)
        audit.record(f"{self.entity_type}.created", entity_type=self.entity_type, entity_id=obj.id,
                     summary=f"Created {self.entity_type} “{self.label(obj)}”", after=obj.to_dict())
        analytics.track(f"{self.entity_type}_created")
        db.session.commit()
        return created(self.serialize(obj))

    def get(self, ident):
        return ok(self.serialize(self.get_or_404(ident)))

    def update(self, ident):
        obj = self.get_or_404(ident)
        model = parse(self.patch_schema)
        changes = provided(model)
        before = obj.to_dict()
        changes = self.prepare_update(obj, changes)
        self.validate_refs(changes)
        if self.custom_fields and "custom" in changes:
            changes["custom"] = cf_service.validate(g.workspace.id, self.entity_type, changes["custom"], obj.custom, partial=True)
        for k, v in changes.items():
            setattr(obj, k, v)
        db.session.flush()
        self.after_update(obj, before, changes)
        b, a = audit.diff(before, obj.to_dict())
        if a:
            audit.record(f"{self.entity_type}.updated", entity_type=self.entity_type, entity_id=obj.id,
                         summary=f"Updated {self.entity_type} “{self.label(obj)}”", before=b, after=a)
        db.session.commit()
        return ok(self.serialize(obj))

    def delete(self, ident):
        obj = self.get_or_404(ident)
        self.before_delete(obj)
        snapshot = obj.to_dict()
        if self.soft_delete:
            from app.models.base import utcnow

            obj.deleted_at = utcnow()
        else:
            db.session.delete(obj)
        self.after_delete(obj)
        audit.record(f"{self.entity_type}.deleted", entity_type=self.entity_type, entity_id=ident,
                     summary=f"Deleted {self.entity_type} “{self.label(obj)}”", before=snapshot)
        db.session.commit()
        return no_content()

    def bulk(self):
        body = request.get_json(silent=True) or {}
        ids = body.get("ids") or []
        action = body.get("action")
        if not isinstance(ids, list) or not ids or len(ids) > 500:
            raise bad_request("Select between 1 and 500 records", "invalid_selection")
        try:
            ids = [uuid.UUID(str(i)) for i in ids]
        except ValueError:
            raise bad_request("Invalid id in selection", "invalid_selection")
        rows = db.session.scalars(self.base_query().where(self.model.id.in_(ids))).unique().all()
        value = body.get("value")
        if action == "delete":
            require(f"{self.name}.delete")
            from app.models.base import utcnow

            for o in rows:
                self.before_delete(o)
                o.deleted_at = utcnow()
            audit.record(f"{self.entity_type}.bulk_deleted", entity_type=self.entity_type, summary=f"Deleted {len(rows)} {self.name}",
                         before={"ids": [str(o.id) for o in rows]})
        else:
            require(f"{self.name}.update")
            if action == "assign" and self.owner_field:
                try:
                    uid = uuid.UUID(str(value)) if value else None
                except ValueError:
                    raise bad_request("Invalid owner")
                ensure_member(uid)
                for o in rows:
                    setattr(o, self.owner_field, uid)
            elif action in ("add_tags", "remove_tags") and hasattr(self.model, "tags"):
                tags = [str(t).strip()[:40] for t in (value or []) if str(t).strip()]
                for o in rows:
                    cur = list(o.tags or [])
                    o.tags = sorted(set(cur) | set(tags)) if action == "add_tags" else [t for t in cur if t not in tags]
                if action == "add_tags":
                    from app.services.tags import ensure_tags

                    ensure_tags(tags)
            elif action == "set" and isinstance(value, dict) and set(value) <= self.bulk_fields:
                for o in rows:
                    changes = self.prepare_update(o, dict(value))
                    before = o.to_dict()
                    for k, v in changes.items():
                        setattr(o, k, v)
                    db.session.flush()
                    self.after_update(o, before, changes)
            else:
                raise bad_request("Unsupported bulk action", "invalid_action")
            audit.record(f"{self.entity_type}.bulk_{action}", entity_type=self.entity_type, summary=f"Bulk {action} on {len(rows)} {self.name}",
                         after={"ids": [str(o.id) for o in rows], "value": value})
        db.session.commit()
        return ok({"affected": len(rows)})

    def export(self):
        require("data.export")
        q = self.apply_sort(self.apply_filters(self.apply_search(self.base_query())))
        rows = db.session.scalars(q.limit(50000)).unique().all()
        users = users_map({getattr(o, self.owner_field) for o in rows} if self.owner_field else set())
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([h for h, _ in self.export_columns])
        for o in rows:
            o._owner_name = users.get(getattr(o, self.owner_field), {}).get("name") if self.owner_field else None  # type: ignore[attr-defined]
            w.writerow([_csv_safe(fn(o)) for _, fn in self.export_columns])
        audit.record(f"{self.entity_type}.exported", entity_type=self.entity_type, summary=f"Exported {len(rows)} {self.name} to CSV")
        db.session.commit()
        return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{self.name}.csv"'})

    # ---- routing -----------------------------------------------------------------------
    def register(self, bp: Blueprint) -> None:
        n = self.name
        bp.add_url_rule("", f"{n}_list", protect(f"{n}.read")(self.list), methods=["GET"])
        bp.add_url_rule("", f"{n}_create", protect(f"{n}.create")(self.create), methods=["POST"])
        bp.add_url_rule("/<uuid:ident>", f"{n}_get", protect(f"{n}.read")(self.get), methods=["GET"])
        bp.add_url_rule("/<uuid:ident>", f"{n}_update", protect(f"{n}.update")(self.update), methods=["PATCH"])
        bp.add_url_rule("/<uuid:ident>", f"{n}_delete", protect(f"{n}.delete")(self.delete), methods=["DELETE"])
        bp.add_url_rule("/bulk", f"{n}_bulk", protect(f"{n}.read")(self.bulk), methods=["POST"])
        bp.add_url_rule("/export", f"{n}_export", protect(f"{n}.read", allow_restricted=True)(self.export), methods=["GET"])


def _csv_safe(v: Any) -> Any:
    """Neutralise spreadsheet formula injection in exported cells."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    if isinstance(v, (list, tuple)):
        return ", ".join(map(str, v))
    return "" if v is None else v
