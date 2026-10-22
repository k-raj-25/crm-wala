"""Calling through the company number: call state for live calls, and who each member reports to (for call hand-overs).

Revision ID: 0008_company_calling
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0008_company_calling"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("data", pg.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.create_index("ix_calls_provider_call_id", "calls", ["provider", "provider_call_id"], postgresql_where=sa.text("provider_call_id IS NOT NULL"))
    op.add_column("workspace_members", sa.Column("reports_to", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")))


def downgrade() -> None:
    op.drop_column("workspace_members", "reports_to")
    op.drop_index("ix_calls_provider_call_id", "calls")
    op.drop_column("calls", "data")
