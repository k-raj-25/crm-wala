"""WhatsApp runs only against a real Meta number: disconnect any WhatsApp integration left in sandbox mode.

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL app.bypass_rls = 'on'")
    op.execute(
        "UPDATE integrations SET status = 'not_connected', mode = 'live', credentials_enc = NULL, config = '{}'::jsonb, "
        "account_label = NULL, last_error = NULL WHERE provider = 'whatsapp' AND (mode = 'sandbox' OR credentials_enc IS NULL)"
    )


def downgrade() -> None:
    pass
