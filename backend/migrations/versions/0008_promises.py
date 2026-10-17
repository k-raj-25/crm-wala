"""Promise ledger: every promise a rep makes to a buyer, approved or rejected by a manager.

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

PREDICATE = (
    "(workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def upgrade() -> None:
    uid = lambda name, table, ondelete="SET NULL": sa.Column(name, pg.UUID(as_uuid=True), sa.ForeignKey(f"{table}.id", ondelete=ondelete))  # noqa: E731
    op.create_table(
        "promises",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), index=True),
        uid("lead_id", "leads"), uid("contact_id", "contacts"), uid("deal_id", "deals"), uid("project_id", "projects"), uid("unit_id", "units"),
        sa.Column("kind", sa.String(20), nullable=False, server_default="other"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("details", sa.Text),
        sa.Column("value", sa.Numeric(16, 2)),
        uid("promised_by", "users"),
        sa.Column("promised_on", sa.Date),
        sa.Column("source", sa.String(15), nullable=False, server_default="manual"),
        sa.Column("source_text", sa.Text),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending", index=True),
        uid("created_by", "users"), uid("decided_by", "users"),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.String(500)),
    )
    for col in ("lead_id", "contact_id", "deal_id", "promised_by"):
        op.create_index(f"ix_promises_{col}", "promises", [col])
    op.execute("ALTER TABLE promises ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE promises FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON promises USING {PREDICATE} WITH CHECK {PREDICATE}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON promises")
    op.drop_table("promises")
