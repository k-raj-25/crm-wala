"""A video link per project (walkthrough or drone video).

Revision ID: 0010_project_video_url
Revises: 0009_project_sizes
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_project_video_url"
down_revision = "0009_project_sizes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("video_url", sa.String(500)))


def downgrade() -> None:
    op.drop_column("projects", "video_url")
