"""Flat sizes on offer per project (each with an optional floor plan file).

Revision ID: 0009_project_sizes
Revises: 0008_company_calling
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0009_project_sizes"
down_revision = "0008_company_calling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("sizes", pg.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False))


def downgrade() -> None:
    op.drop_column("projects", "sizes")
