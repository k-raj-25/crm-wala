from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.extensions import Base, db


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


class Timestamps:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )


class SoftDelete:
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class Tenant:
    """Marks a table as tenant-owned. RLS policies are created for these in migrations."""

    __tenant__ = True

    @declared_attr
    def workspace_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
        )


def _jsonable(v: Any) -> Any:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_jsonable(i) for i in v]
    if isinstance(v, dict):
        return {k: _jsonable(i) for k, i in v.items()}
    return v


class Serializable:
    __hidden__: tuple[str, ...] = ()

    def to_dict(self, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
        skip = set(self.__hidden__) | set(exclude)
        return {c.key: _jsonable(getattr(self, c.key)) for c in self.__table__.columns if c.key not in skip}  # type: ignore[attr-defined]


__all__ = ["Base", "db", "UUIDPk", "Timestamps", "SoftDelete", "Tenant", "Serializable", "utcnow"]
