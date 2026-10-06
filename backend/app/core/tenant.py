"""Tenant context + Postgres row-level-security wiring.

Every tenant table has an RLS policy keyed on the `app.current_workspace_id`
setting. This module sets that setting for each transaction so that even a
buggy query (missing `workspace_id` filter) cannot cross tenant boundaries.
`bypass` is only used by the Super Admin app, background jobs and seeders.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.extensions import db


@dataclass(frozen=True)
class TenantCtx:
    workspace_id: str | None = None
    bypass: bool = False


_ctx: ContextVar[TenantCtx] = ContextVar("tenant_ctx", default=TenantCtx())

_SET_SQL = text("SELECT set_config('app.current_workspace_id', :w, true), set_config('app.bypass_rls', :b, true)")


def current() -> TenantCtx:
    return _ctx.get()


def _apply(connection) -> None:
    c = _ctx.get()
    connection.execute(_SET_SQL, {"w": c.workspace_id or "", "b": "on" if c.bypass else "off"})


def set_tenant(workspace_id: uuid.UUID | str | None, *, bypass: bool = False) -> None:
    _ctx.set(TenantCtx(str(workspace_id) if workspace_id else None, bypass))
    # Re-apply inside a transaction that may already have started (e.g. auth lookup).
    if db.session().in_transaction():
        _apply(db.session.connection())


def clear_tenant() -> None:
    set_tenant(None)


@contextmanager
def tenant_scope(workspace_id: uuid.UUID | str | None, *, bypass: bool = False):
    prev = _ctx.get()
    set_tenant(workspace_id, bypass=bypass)
    try:
        yield
    finally:
        _ctx.set(prev)
        if db.session().in_transaction():
            _apply(db.session.connection())


def bypass_scope():
    return tenant_scope(None, bypass=True)


@event.listens_for(Session, "after_begin")
def _after_begin(session, transaction, connection):  # pragma: no cover - exercised implicitly
    _apply(connection)
