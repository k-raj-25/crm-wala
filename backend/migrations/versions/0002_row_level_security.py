"""Row-level security: database-enforced tenant isolation.

Each tenant table only exposes rows whose workspace_id equals the transaction-local
`app.current_workspace_id` setting. If the setting is missing the policy evaluates to NULL
and NO rows are visible (fail closed). `app.bypass_rls = 'on'` is reserved for the Super
Admin app, background jobs and seeders. FORCE makes the policy apply to the table owner too.
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "activities", "ai_conversations", "ai_usage", "automation_runs", "automations", "calls", "companies",
    "contacts", "crm_email_templates", "custom_field_defs", "deals", "duplicate_dismissals", "emails", "files",
    "import_jobs", "integrations", "leads", "meetings", "notes", "notifications", "pipeline_stages", "pipelines",
    "saved_reports", "saved_views", "tags", "tasks", "teams",
    "subscriptions", "payments", "invoices", "checkout_sessions",
]

PREDICATE = (
    "(workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def upgrade():
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING {PREDICATE} WITH CHECK {PREDICATE}")


def downgrade():
    for t in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
