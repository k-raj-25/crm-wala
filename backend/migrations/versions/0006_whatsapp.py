"""WhatsApp Business (Meta Cloud API): message log, and brochures / floor plans attached to projects and units.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

PREDICATE = (
    "(workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def upgrade() -> None:
    # Files can belong to a project or a unit, tagged as a brochure / floor plan so they can be sent from the unit drawer.
    op.add_column("files", sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE")))
    op.add_column("files", sa.Column("unit_id", pg.UUID(as_uuid=True), sa.ForeignKey("units.id", ondelete="CASCADE")))
    op.add_column("files", sa.Column("doc_kind", sa.String(20)))
    op.create_index("ix_files_project_id", "files", ["project_id"])
    op.create_index("ix_files_unit_id", "files", ["unit_id"])

    op.create_table(
        "whatsapp_messages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lead_id", pg.UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="CASCADE"), index=True),
        sa.Column("contact_id", pg.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="CASCADE"), index=True),
        sa.Column("company_id", pg.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True),
        sa.Column("deal_id", pg.UUID(as_uuid=True), sa.ForeignKey("deals.id", ondelete="CASCADE"), index=True),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("status", sa.String(15), nullable=False),
        sa.Column("kind", sa.String(15), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("template_name", sa.String(120)),
        sa.Column("template_language", sa.String(15)),
        sa.Column("file_id", pg.UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="SET NULL")),
        sa.Column("unit_id", pg.UUID(as_uuid=True), sa.ForeignKey("units.id", ondelete="SET NULL")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("wa_message_id", sa.String(200)),
        sa.Column("error", sa.String(400)),
        sa.Column("data", pg.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.create_index("ix_whatsapp_messages_ws_phone", "whatsapp_messages", ["workspace_id", "phone", "created_at"])
    op.create_index("uq_whatsapp_messages_wamid", "whatsapp_messages", ["workspace_id", "wa_message_id"], unique=True,
                    postgresql_where=sa.text("wa_message_id IS NOT NULL"))
    op.execute("ALTER TABLE whatsapp_messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE whatsapp_messages FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON whatsapp_messages USING {PREDICATE} WITH CHECK {PREDICATE}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON whatsapp_messages")
    op.drop_table("whatsapp_messages")
    op.drop_index("ix_files_unit_id", "files")
    op.drop_index("ix_files_project_id", "files")
    op.drop_column("files", "doc_kind")
    op.drop_column("files", "unit_id")
    op.drop_column("files", "project_id")
