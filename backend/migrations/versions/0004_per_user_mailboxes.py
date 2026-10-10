"""Gmail/Outlook connections belong to the individual user, not the whole workspace.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

NIL = "'00000000-0000-0000-0000-000000000000'::uuid"


def upgrade() -> None:
    op.drop_constraint("uq_integration_ws_provider", "integrations", type_="unique")
    # One row per (workspace, provider, connecting user). Workspace-wide integrations (Slack, webhooks...) keep connected_by NULL-able
    # semantics: coalesce makes "no user" a single bucket so they stay unique per workspace.
    op.execute(f"CREATE UNIQUE INDEX uq_integration_ws_provider_user ON integrations (workspace_id, provider, COALESCE(connected_by, {NIL}))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_integration_ws_provider_user")
    op.create_unique_constraint("uq_integration_ws_provider", "integrations", ["workspace_id", "provider"])
