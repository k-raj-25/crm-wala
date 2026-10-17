"""Visit recaps: the page a buyer gets on WhatsApp after a site visit (flats seen, photos, prices, "hold this flat").

Revision ID: 0008_visit_recaps
Revises: 0007

Its own revision id (not "0008") so it doesn't collide with other features branching off 0007 at the same time.
Whichever of them merges second points its down_revision at the one that merged first.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0008_visit_recaps"
down_revision = "0007"
branch_labels = None
depends_on = None

PREDICATE = (
    "(workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def upgrade() -> None:
    uid = lambda name, table, ondelete="SET NULL": sa.Column(name, pg.UUID(as_uuid=True), sa.ForeignKey(f"{table}.id", ondelete=ondelete))
    jsonb = lambda name, default: sa.Column(name, pg.JSONB, server_default=sa.text(f"'{default}'::jsonb"), nullable=False)
    op.create_table(
        "visit_recaps",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        uid("lead_id", "leads", "CASCADE"), uid("contact_id", "contacts", "CASCADE"), uid("company_id", "companies", "CASCADE"), uid("deal_id", "deals", "CASCADE"),
        uid("meeting_id", "meetings"), uid("project_id", "projects"),
        jsonb("unit_ids", "[]"), jsonb("photo_ids", "[]"),
        sa.Column("message", sa.Text),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        uid("created_by", "users"),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("sent_via", sa.String(15)),
        sa.Column("views", sa.Integer, server_default="0", nullable=False),
        sa.Column("first_viewed_at", sa.DateTime(timezone=True)),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True)),
        jsonb("hold_requests", "[]"),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    for col in ("lead_id", "contact_id", "company_id", "deal_id", "meeting_id"):
        op.create_index(f"ix_visit_recaps_{col}", "visit_recaps", [col])
    op.execute("ALTER TABLE visit_recaps ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE visit_recaps FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON visit_recaps USING {PREDICATE} WITH CHECK {PREDICATE}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON visit_recaps")
    op.drop_table("visit_recaps")
