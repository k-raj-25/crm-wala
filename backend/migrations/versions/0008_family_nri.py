"""Family and NRI mode: family members on a buyer, their translated WhatsApp messages and video walkthrough requests.

Revision ID: 0008_family_nri
Revises: 0007

Its own branch off 0007, so it merges alongside other features' 0008 migrations; `flask db upgrade heads` applies them all.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0008_family_nri"
down_revision = "0007"
branch_labels = None
depends_on = None

PREDICATE = (
    "(workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)
TABLES = ("family_members", "family_messages", "walkthroughs")


def _base() -> list:
    return [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    uid = lambda name, table, ondelete="SET NULL", **kw: sa.Column(name, pg.UUID(as_uuid=True), sa.ForeignKey(f"{table}.id", ondelete=ondelete), **kw)  # noqa: E731
    op.create_table(
        "family_members", *_base(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), index=True),
        uid("lead_id", "leads", "CASCADE", index=True), uid("contact_id", "contacts", "CASCADE", index=True), uid("deal_id", "deals", "CASCADE", index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("relation", sa.String(20), nullable=False, server_default="other"),
        sa.Column("role", sa.String(12), nullable=False, server_default="decides"),
        sa.Column("phone", sa.String(40)),
        sa.Column("email", sa.String(254)),
        sa.Column("language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Kolkata"),
        sa.Column("city", sa.String(80)),
        sa.Column("is_nri", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("checklist", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("notes", sa.Text),
        sa.Column("link_token", sa.String(64), unique=True),
        uid("created_by", "users"),
    )
    op.create_table(
        "family_messages", *_base(),
        uid("member_id", "family_members", "CASCADE", index=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="scheduled", index=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("original", sa.Text),
        sa.Column("language", sa.String(8), nullable=False, server_default="en"),
        sa.Column("template", pg.JSONB),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        uid("whatsapp_message_id", "whatsapp_messages"),
        sa.Column("error", sa.String(400)),
        uid("user_id", "users"),
    )
    op.create_table(
        "walkthroughs", *_base(),
        uid("member_id", "family_members", "CASCADE", index=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="requested", index=True),
        uid("project_id", "projects"), uid("unit_id", "units"),
        sa.Column("note", sa.String(500)),
        sa.Column("requested_via", sa.String(10), nullable=False, server_default="link"),
        sa.Column("meeting_url", sa.String(500)),
        uid("meeting_id", "meetings"),
        uid("decided_by", "users"),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )
    for t in TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING {PREDICATE} WITH CHECK {PREDICATE}")


def downgrade() -> None:
    for t in reversed(TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.drop_table(t)
