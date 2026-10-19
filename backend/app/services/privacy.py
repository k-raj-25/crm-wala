"""Client phone-number privacy, so leads can't walk out of the door with an employee.

When a workspace hides phone numbers (`settings.hide_phones`, on by default), only members with `phones.view` get a
client's real number from the API. Everyone else gets a masked one (`+91 ••••• •••10`) and works the client through
the CRM (WhatsApp, logged calls), where the server looks the real number up itself. Members with `phones.reveal`
can reveal one number at a time, and each reveal is written to the audit log.

Masking happens on the server, at every place a number leaves it, so it can't be undone from the browser.
Server-side work (sending WhatsApp, automations, webhooks, imports) never goes through this and keeps the real number.
"""
from __future__ import annotations

import re
from typing import Any

from flask import g, has_request_context

from app.core.errors import ApiError, forbidden
from app.core.permissions import has_permission
from app.services import custom_fields as cf_service

DOT = "•"
PHONE_ENTITIES = ("lead", "contact", "company", "call")
CUSTOM_ENTITIES = ("lead", "contact", "company")


def hidden_for_workspace(ws) -> bool:
    return bool((ws.settings or {}).get("hide_phones", True)) if ws is not None else False


def _member_context() -> bool:
    return has_request_context() and getattr(g, "user", None) is not None and getattr(g, "workspace", None) is not None


def can_view() -> bool:
    """True when the current member may see full phone numbers (always true outside a member's request)."""
    if not _member_context() or not hidden_for_workspace(g.workspace):
        return True
    return has_permission(getattr(g, "permissions", set()), "phones.view")


def can_reveal() -> bool:
    return can_view() or has_permission(getattr(g, "permissions", set()), "phones.reveal")


def mask(raw: Any) -> Any:
    """`+91 98765 43210` -> `+91 ••••• •••10`. Keeps the country code and last two digits so records can be told apart."""
    if not raw or not isinstance(raw, str):
        return raw
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 4:
        return DOT * 3
    cc = digits[:-10] if raw.strip().startswith("+") and len(digits) > 10 else ""
    return (f"+{cc} " if cc else "") + f"{DOT * 5} {DOT * 3}{digits[-2:]}"


def is_masked(v: Any) -> bool:
    return isinstance(v, str) and DOT in v


def _phone_custom_keys(entity_type: str) -> list[str]:
    if entity_type not in CUSTOM_ENTITIES or not _member_context():
        return []
    cache = g.__dict__.setdefault("_phone_cf_keys", {})
    if entity_type not in cache:
        cache[entity_type] = [d.key for d in cf_service.definitions(g.workspace.id, entity_type) if d.field_type == "phone"]
    return cache[entity_type]


def mask_records(entity_type: str, dicts: list[dict]) -> list[dict]:
    """Mask `phone` and phone-type custom fields in serialized records for members who can't see numbers."""
    if entity_type not in PHONE_ENTITIES or can_view():
        return dicts
    keys = _phone_custom_keys(entity_type)
    for d in dicts:
        if d.get("phone"):
            d["phone"] = mask(d["phone"])
            d["phone_masked"] = True
        custom = d.get("custom")
        if keys and isinstance(custom, dict):
            d["custom"] = {k: (mask(v) if k in keys else v) for k, v in custom.items()}
    return dicts


_PHONE_TEXT = re.compile(r"(?<![\w])(\+?\d[\d\s-]{8,}\d)(?![\w])")
_PHONE_KEYS = {"phone", "mobile"}
_WA_KEYS = {"whatsapp", "whatsapp_url"}


def _scrub(v: Any, key: str | None = None) -> Any:
    if isinstance(v, dict):
        return {k: _scrub(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [_scrub(x) for x in v]
    if not isinstance(v, str) or not v:
        return v
    if key in _PHONE_KEYS:
        return mask(v)
    if key in _WA_KEYS and "wa.me/" in v:
        return None  # a wa.me link carries the number in its URL
    return _PHONE_TEXT.sub(lambda m: mask(m.group(1)) if len(re.sub(r"\D", "", m.group(1))) >= 10 else m.group(1), v)


def mask_response(resp):
    """after_request hook for blueprints whose payloads mention numbers in free-form places (the AI features):
    masks `phone` fields, drops wa.me links and masks phone numbers written inside text."""
    if can_view() or not resp.is_json:
        return resp
    data = resp.get_json(silent=True)
    if data is not None:
        import json

        resp.set_data(json.dumps(_scrub(data)))
    return resp


def mask_text(text: str) -> str:
    """Free text for the current member (e.g. a WhatsApp reply): numbers written inside it are masked unless they may see them."""
    return text if can_view() else _scrub(text)


def mask_value(v: Any) -> Any:
    return v if can_view() else mask(v)


def guard_changes(entity_type: str, obj, changes: dict) -> dict:
    """Stop members who can't see numbers from wiping or overwriting one they can't see.

    A masked or blank phone in an edit keeps the saved number. A new number can only be added where none is saved yet.
    """
    if entity_type not in PHONE_ENTITIES or can_view():
        return changes
    if "phone" in changes:
        v = changes["phone"]
        if v in (None, "") or is_masked(v) or (v == obj.phone):
            changes.pop("phone")
        elif obj.phone:
            raise forbidden("Only someone who can see phone numbers can change a saved number.", "phone_hidden")
    keys = _phone_custom_keys(entity_type)
    if keys and isinstance(changes.get("custom"), dict):
        saved = obj.custom or {}
        custom = dict(changes["custom"])
        for k in keys:
            if k not in custom:
                continue
            v = custom[k]
            if v in (None, "") or is_masked(v) or v == saved.get(k):
                custom.pop(k)
            elif saved.get(k):
                raise forbidden("Only someone who can see phone numbers can change a saved number.", "phone_hidden")
        changes["custom"] = custom
    return changes


def reveal(entity_type: str, obj) -> dict:
    """Return the real number(s) of one record and log who looked."""
    from app.services import audit

    if not can_reveal():
        raise forbidden("Your role can't see clients' phone numbers.", "phone_hidden")
    if entity_type not in CUSTOM_ENTITIES:
        raise ApiError(400, "bad_request", "This record has no phone number")
    keys = _phone_custom_keys(entity_type)
    custom = {k: v for k, v in (getattr(obj, "custom", None) or {}).items() if k in keys and v}
    name = getattr(obj, "name", None) or entity_type
    if not can_view():
        audit.record("phone.revealed", entity_type=entity_type, entity_id=obj.id, summary=f"Viewed the phone number of {name}")
    return {"phone": obj.phone, "custom": custom}
