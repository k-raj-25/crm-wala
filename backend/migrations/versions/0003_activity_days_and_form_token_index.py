"""user activity days (DAU/WAU/MAU) + lookup index for public lead-capture form tokens"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_activity_days",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("user_id", "day"),
    )
    op.create_index("ix_user_activity_days_workspace_id", "user_activity_days", ["workspace_id"])
    op.create_index("ix_user_activity_days_day", "user_activity_days", ["day"])
    op.execute("CREATE INDEX ix_workspaces_form_token ON workspaces ((settings->>'public_form_token'))")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_workspaces_form_token")
    op.drop_table("user_activity_days")
