from __future__ import annotations

from app.core.crud import users_map
from app.services.related import attach_related


def activity_dicts(rows: list) -> list[dict]:
    users = users_map({r.user_id for r in rows})
    out = []
    for r in rows:
        d = r.to_dict()
        d["user"] = users.get(r.user_id)
        out.append(d)
    attach_related(rows, out)
    return out
