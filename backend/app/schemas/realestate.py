from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import Schema, patchify

ProjectKind = Literal["residential", "commercial", "villa", "plotted", "mixed"]
ProjectStage = Literal["upcoming", "under_construction", "ready"]
UnitKind = Literal["apartment", "villa", "shop", "office", "plot"]
UnitStatus = Literal["vacant", "for_sale", "for_rent", "on_hold", "booked", "sold", "rented", "self_occupied"]
Money = decimal.Decimal | None


class ProjectIn(Schema):
    name: str = Field(min_length=1, max_length=160)
    developer: str | None = Field(default=None, max_length=160)
    kind: ProjectKind = "residential"
    stage: ProjectStage = "ready"
    city: str | None = Field(default=None, max_length=80)
    locality: str | None = Field(default=None, max_length=120)
    sector: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    rera_id: str | None = Field(default=None, max_length=80)
    possession_date: dt.date | None = None
    amenities: list[str] = Field(default_factory=list, max_length=40)
    description: str | None = Field(default=None, max_length=10000)
    cover_url: str | None = Field(default=None, max_length=500)
    owner_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=25)

    @field_validator("amenities", "tags")
    @classmethod
    def _clean(cls, v):
        return [t.strip()[:60] for t in v if t and t.strip()]


ProjectPatch = patchify(ProjectIn, "ProjectPatch")


class TowerIn(Schema):
    name: str = Field(min_length=1, max_length=80)
    floors: int = Field(default=10, ge=0, le=120, description="Floors above the ground floor")
    units_per_floor: int = Field(default=4, ge=1, le=24)
    has_ground: bool = True
    # Defaults stamped on every generated unit (edit individually afterwards)
    kind: UnitKind = "apartment"
    bhk: str | None = Field(default=None, max_length=20)
    area_sqft: decimal.Decimal | None = Field(default=None, ge=0, le=decimal.Decimal("9999999"))
    sale_price: decimal.Decimal | None = Field(default=None, ge=0)
    monthly_rent: decimal.Decimal | None = Field(default=None, ge=0)
    status: UnitStatus = "vacant"


class TowerPatch(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    status: Literal["active", "upcoming", "completed"] | None = None


class AddFloorsIn(Schema):
    count: int = Field(default=1, ge=1, le=20)
    units_per_floor: int = Field(default=4, ge=1, le=24)


class UnitIn(Schema):
    tower_id: uuid.UUID
    floor: int = Field(default=1, ge=0, le=150)
    number: str = Field(min_length=1, max_length=20)
    kind: UnitKind = "apartment"
    bhk: str | None = Field(default=None, max_length=20)
    area_sqft: decimal.Decimal | None = Field(default=None, ge=0, le=decimal.Decimal("9999999"))
    facing: str | None = Field(default=None, max_length=20)
    status: UnitStatus = "vacant"
    sale_price: Money = Field(default=None, ge=0)
    monthly_rent: Money = Field(default=None, ge=0)
    owner_contact_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=25)


class UnitPatchIn(Schema):
    number: str | None = Field(default=None, min_length=1, max_length=20)
    kind: UnitKind | None = None
    bhk: str | None = Field(default=None, max_length=20)
    area_sqft: Money = Field(default=None, ge=0, le=decimal.Decimal("9999999"))
    facing: str | None = Field(default=None, max_length=20)
    status: UnitStatus | None = None
    sale_price: Money = Field(default=None, ge=0)
    monthly_rent: Money = Field(default=None, ge=0)
    owner_contact_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = Field(default=None, max_length=25)


class StatusIn(Schema):
    status: UnitStatus
    note: str | None = Field(default=None, max_length=500)
    lead_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    hold_hours: int | None = Field(default=None, ge=1, le=24 * 30)
