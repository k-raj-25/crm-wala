"""Airline-style pricing: price suggestions the owner applied, dismissed or undone.

Revision ID: 0009_price_changes
Revises: 0007

Branches off 0007 on purpose, so it doesn't depend on other features in flight. If another migration lands on 0007 first,
point down_revision at that one before merging (a single head keeps `flask db upgrade` working).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0009_price_changes"
down_revision = "0007"
branch_labels = None
depends_on = None

PREDICATE = (
    "(workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def upgrade() -> None:
    op.create_table(
        "price_changes",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tower_id", pg.UUID(as_uuid=True), sa.ForeignKey("towers.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(12), nullable=False, server_default="applied", index=True),
        sa.Column("rule", sa.String(20), nullable=False),
        sa.Column("segment_key", sa.String(200), nullable=False, index=True),
        sa.Column("segment_label", sa.String(200), nullable=False),
        sa.Column("pct", sa.Numeric(6, 2), nullable=False),
        sa.Column("headline", sa.String(400)),
        sa.Column("evidence", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("units", pg.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("decided_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("undone_at", sa.DateTime(timezone=True)),
        sa.Column("undone_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.execute("ALTER TABLE price_changes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE price_changes FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON price_changes USING {PREDICATE} WITH CHECK {PREDICATE}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON price_changes")
    op.drop_table("price_changes")
