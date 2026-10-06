from __future__ import annotations

import datetime as dt
import re
from typing import Any

from app.core.errors import ApiError
from app.extensions import db
from app.models import CustomFieldDef

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL = re.compile(r"^https?://[^\s]+$", re.I)
_PHONE = re.compile(r"^[+\d][\d\s().-]{5,}$")
TYPES = ["text", "number", "currency", "date", "dropdown", "multi_select", "checkbox", "url", "email", "phone"]


def definitions(workspace_id, entity_type: str) -> list[CustomFieldDef]:
    return db.session.query(CustomFieldDef).filter_by(workspace_id=workspace_id, entity_type=entity_type).order_by(CustomFieldDef.position).all()


def _coerce(d: CustomFieldDef, v: Any) -> Any:
    t = d.field_type
    if t in ("text",):
        return str(v)[:2000]
    if t in ("number", "currency"):
        return float(v)
    if t == "checkbox":
        if isinstance(v, bool):
            return v
        raise ValueError("must be true or false")
    if t == "date":
        dt.date.fromisoformat(str(v)[:10])
        return str(v)[:10]
    if t == "dropdown":
        if v not in d.options:
            raise ValueError("choose one of the listed options")
        return v
    if t == "multi_select":
        if not isinstance(v, list) or any(i not in d.options for i in v):
            raise ValueError("choose from the listed options")
        return v
    if t == "url":
        if not _URL.match(str(v)):
            raise ValueError("must be a valid http(s) URL")
        return str(v)
    if t == "email":
        if not _EMAIL.match(str(v)):
            raise ValueError("must be a valid email")
        return str(v)
    if t == "phone":
        if not _PHONE.match(str(v)):
            raise ValueError("must be a valid phone number")
        return str(v)
    return v


def validate(workspace_id, entity_type: str, values: dict | None, existing: dict | None = None, *, partial: bool = False) -> dict:
    """Validate custom-field values against workspace definitions; unknown keys are rejected."""
    defs = {d.key: d for d in definitions(workspace_id, entity_type)}
    merged = dict(existing or {})
    errors: dict[str, str] = {}
    for k, v in (values or {}).items():
        d = defs.get(k)
        if d is None:
            errors[f"custom.{k}"] = "Unknown custom field"
            continue
        if v in (None, "", []):
            merged.pop(k, None)
            continue
        try:
            merged[k] = _coerce(d, v)
        except (ValueError, TypeError) as e:
            errors[f"custom.{k}"] = f"{d.label}: {e}"
    for k, d in defs.items():
        if partial and k not in (values or {}):
            continue
        if d.required and merged.get(k) in (None, "", []):
            errors[f"custom.{k}"] = f"{d.label} is required"
    if errors:
        raise ApiError(422, "validation_error", "Please check the highlighted fields", errors)
    return merged
