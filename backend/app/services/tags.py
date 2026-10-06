from __future__ import annotations

import itertools

from flask import g

from app.extensions import db
from app.models import Tag

_PALETTE = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6"]


def ensure_tags(names: list[str]) -> None:
    names = {n.strip()[:40] for n in names if n and n.strip()}
    if not names:
        return
    existing = {t.name for t in db.session.query(Tag.name).filter(Tag.workspace_id == g.workspace.id, Tag.name.in_(names))}
    colors = itertools.cycle(_PALETTE)
    count = db.session.query(Tag).filter_by(workspace_id=g.workspace.id).count()
    for _ in range(count % len(_PALETTE)):
        next(colors)
    for n in sorted(names - existing):
        db.session.add(Tag(workspace_id=g.workspace.id, name=n, color=next(colors)))
