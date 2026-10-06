from __future__ import annotations

from typing import Any

from app.core.features import DEFAULT_PLATFORM_SETTINGS
from app.extensions import db
from app.models import PlatformSetting


def get_setting(key: str, field: str = "value", default: Any = None) -> Any:
    row = db.session.get(PlatformSetting, key)
    if row is not None and field in row.value:
        return row.value[field]
    if key in DEFAULT_PLATFORM_SETTINGS:
        return DEFAULT_PLATFORM_SETTINGS[key][0].get(field, default)
    return default


def trial_days() -> int:
    return int(get_setting("trial_days", default=3))


def grace_days() -> int:
    return int(get_setting("grace_days", default=3))
