"""Real estate: projects, towers, units, unit history; client requirements on leads; unit links on deals and site visits.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

NEW_TABLES = ["projects", "towers", "units", "unit_events"]
PREDICATE = (
    "(workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def _base():
    return [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
    ]


def _ts():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "projects", *_base(), *_ts(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), index=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("developer", sa.String(160)),
        sa.Column("kind", sa.String(15), server_default="residential", nullable=False),
        sa.Column("stage", sa.String(20), server_default="ready", nullable=False),
        sa.Column("city", sa.String(80), index=True),
        sa.Column("locality", sa.String(120)),
        sa.Column("sector", sa.String(120)),
        sa.Column("address", sa.String(300)),
        sa.Column("rera_id", sa.String(80)),
        sa.Column("possession_date", sa.Date),
        sa.Column("amenities", pg.ARRAY(sa.String), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("cover_url", sa.String(500)),
        sa.Column("owner_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
        sa.Column("tags", pg.ARRAY(sa.String), server_default=sa.text("'{}'"), nullable=False),
    )
    op.create_table(
        "towers", *_base(), *_ts(),
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("floors", sa.Integer, server_default="1", nullable=False),
        sa.Column("has_ground", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("status", sa.String(15), server_default="active", nullable=False),
        sa.Column("position", sa.Integer, server_default="0", nullable=False),
        sa.UniqueConstraint("project_id", "name", name="uq_tower_project_name"),
    )
    op.create_table(
        "units", *_base(), *_ts(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), index=True),
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tower_id", pg.UUID(as_uuid=True), sa.ForeignKey("towers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("floor", sa.Integer, server_default="0", nullable=False),
        sa.Column("position", sa.Integer, server_default="0", nullable=False),
        sa.Column("number", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(15), server_default="apartment", nullable=False),
        sa.Column("bhk", sa.String(20)),
        sa.Column("area_sqft", sa.Numeric(10, 2)),
        sa.Column("facing", sa.String(20)),
        sa.Column("status", sa.String(15), server_default="vacant", nullable=False, index=True),
        sa.Column("sale_price", sa.Numeric(16, 2)),
        sa.Column("monthly_rent", sa.Numeric(16, 2)),
        sa.Column("owner_contact_id", pg.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="SET NULL"), index=True),
        sa.Column("occupant_contact_id", pg.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="SET NULL")),
        sa.Column("hold_lead_id", pg.UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="SET NULL")),
        sa.Column("hold_until", sa.DateTime(timezone=True), index=True),
        sa.Column("held_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status_changed_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text),
        sa.Column("tags", pg.ARRAY(sa.String), server_default=sa.text("'{}'"), nullable=False),
        sa.UniqueConstraint("tower_id", "number", name="uq_unit_tower_number"),
    )
    op.create_index("ix_units_project_status", "units", ["project_id", "status"])
    op.create_table(
        "unit_events", *_base(),
        sa.Column("unit_id", pg.UUID(as_uuid=True), sa.ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("from_status", sa.String(15)),
        sa.Column("to_status", sa.String(15)),
        sa.Column("note", sa.String(500)),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("lead_id", pg.UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="SET NULL")),
        sa.Column("contact_id", pg.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, index=True),
    )

    # Client requirement on a lead
    op.add_column("leads", sa.Column("intent", sa.String(10)))
    op.add_column("leads", sa.Column("property_type", sa.String(20)))
    op.add_column("leads", sa.Column("bhk", sa.String(20)))
    op.add_column("leads", sa.Column("budget_min", sa.Numeric(16, 2)))
    op.add_column("leads", sa.Column("budget_max", sa.Numeric(16, 2)))
    op.add_column("leads", sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL")))
    op.add_column("leads", sa.Column("unit_id", pg.UUID(as_uuid=True), sa.ForeignKey("units.id", ondelete="SET NULL")))
    op.create_index("ix_leads_project_id", "leads", ["project_id"])
    op.create_index("ix_leads_unit_id", "leads", ["unit_id"])

    # Deals (bookings) and site visits point at the unit
    for t in ("deals", "meetings"):
        op.add_column(t, sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL")))
        op.add_column(t, sa.Column("unit_id", pg.UUID(as_uuid=True), sa.ForeignKey("units.id", ondelete="SET NULL")))
        op.create_index(f"ix_{t}_project_id", t, ["project_id"])
        op.create_index(f"ix_{t}_unit_id", t, ["unit_id"])
    op.add_column("meetings", sa.Column("kind", sa.String(15), server_default="meeting", nullable=False))

    for t in NEW_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING {PREDICATE} WITH CHECK {PREDICATE}")


def downgrade() -> None:
    for t in NEW_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
    op.drop_column("meetings", "kind")
    for t in ("meetings", "deals"):
        op.drop_index(f"ix_{t}_unit_id", t)
        op.drop_index(f"ix_{t}_project_id", t)
        op.drop_column(t, "unit_id")
        op.drop_column(t, "project_id")
    op.drop_index("ix_leads_unit_id", "leads")
    op.drop_index("ix_leads_project_id", "leads")
    for c in ("unit_id", "project_id", "budget_max", "budget_min", "bhk", "property_type", "intent"):
        op.drop_column("leads", c)
    for t in ("unit_events", "units", "towers", "projects"):
        op.drop_table(t)
