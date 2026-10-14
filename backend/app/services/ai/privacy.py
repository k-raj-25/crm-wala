"""Optional masking of phone numbers and email addresses before CRM data is sent to the workspace's AI provider."""
from __future__ import annotations

import re

from flask import g, has_request_context

_EMAIL = re.compile(r"([\w.+-])[\w.+-]*@([\w-]+\.[\w.-]+)")
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s-]{6,}\d)(?!\d)")
_KEYS = {"email", "phone", "mobile", "to_addresses", "from_address"}


def enabled() -> bool:
    if not has_request_context() or getattr(g, "workspace", None) is None:
        return False
    from app.services.ai import settings

    return settings.resolve().mask_pii


def mask_text(s: str) -> str:
    s = _EMAIL.sub(lambda m: f"{m.group(1)}…@{m.group(2)}", s)
    return _PHONE.sub(lambda m: "•••" + re.sub(r"\D", "", m.group(1))[-3:], s)


def mask(value, force: bool | None = None):
    on = enabled() if force is None else force
    if not on:
        return value
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, list):
        return [mask(v, True) for v in value]
    if isinstance(value, dict):
        return {k: ("•••" if k in _KEYS and v else mask(v, True)) for k, v in value.items()}
    return value
