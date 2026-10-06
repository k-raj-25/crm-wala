"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-06 18:23:20.722390

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS citext')
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.create_table('admin_users',
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), server_default='superadmin', nullable=False),
    sa.Column('totp_secret_enc', sa.Text(), nullable=True),
    sa.Column('totp_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.Column('failed_login_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_ip', sa.String(length=64), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('analytics_events',
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('properties', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('analytics_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_analytics_events_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_analytics_events_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_analytics_events_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_analytics_events_workspace_id'), ['workspace_id'], unique=False)
        batch_op.create_index('ix_analytics_name_created', ['name', 'created_at'], unique=False)

    op.create_table('api_error_logs',
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('method', sa.String(length=10), nullable=False),
    sa.Column('path', sa.String(length=300), nullable=False),
    sa.Column('status', sa.Integer(), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('workspace_id', sa.UUID(), nullable=True),
    sa.Column('request_id', sa.String(length=40), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('api_error_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_error_logs_created_at'), ['created_at'], unique=False)

    op.create_table('audit_logs',
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=True),
    sa.Column('actor_type', sa.String(length=10), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('actor_label', sa.String(length=200), nullable=True),
    sa.Column('impersonator_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=True),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('summary', sa.String(length=400), nullable=True),
    sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=300), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_logs_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_actor_id'), ['actor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_entity_type'), ['entity_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('auth_events',
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('realm', sa.String(length=10), nullable=False),
    sa.Column('event', sa.String(length=40), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('subject_id', sa.UUID(), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=300), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('auth_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_auth_events_created_at'), ['created_at'], unique=False)

    op.create_table('coupons',
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=True),
    sa.Column('percent_off', sa.Integer(), nullable=True),
    sa.Column('amount_off', sa.Integer(), nullable=True),
    sa.Column('currency', sa.String(length=3), server_default='INR', nullable=False),
    sa.Column('duration', sa.String(length=20), server_default='once', nullable=False),
    sa.Column('duration_months', sa.Integer(), nullable=True),
    sa.Column('max_redemptions', sa.Integer(), nullable=True),
    sa.Column('times_redeemed', sa.Integer(), server_default='0', nullable=False),
    sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('plan_keys', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('email_logs',
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=True),
    sa.Column('to_address', sa.String(length=254), nullable=False),
    sa.Column('template_key', sa.String(length=60), nullable=True),
    sa.Column('subject', sa.String(length=300), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=15), nullable=False),
    sa.Column('error', sa.String(length=400), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('email_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_logs_created_at'), ['created_at'], unique=False)

    op.create_table('feature_flags',
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=True),
    sa.Column('enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('rollout_percent', sa.Integer(), server_default='100', nullable=False),
    sa.Column('workspace_overrides', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('job_logs',
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('status', sa.String(length=15), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('job_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_job_logs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_job_logs_name'), ['name'], unique=False)

    op.create_table('permissions',
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('group', sa.String(length=40), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('plans',
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('tagline', sa.String(length=200), nullable=True),
    sa.Column('currency', sa.String(length=3), server_default='INR', nullable=False),
    sa.Column('price_monthly', sa.Integer(), nullable=True),
    sa.Column('price_annual', sa.Integer(), nullable=True),
    sa.Column('limits', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('features', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('highlights', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('is_public', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('is_trial', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('is_custom', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('provider_price_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('platform_email_templates',
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('subject', sa.String(length=300), nullable=False),
    sa.Column('body_html', sa.Text(), nullable=False),
    sa.Column('variables', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('platform_settings',
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('users',
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('google_sub', sa.String(length=64), nullable=True),
    sa.Column('avatar_url', sa.String(length=500), nullable=True),
    sa.Column('job_role', sa.String(length=120), nullable=True),
    sa.Column('phone', sa.String(length=40), nullable=True),
    sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.Column('suspended_reason', sa.String(length=300), nullable=True),
    sa.Column('totp_secret_enc', sa.Text(), nullable=True),
    sa.Column('totp_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('failed_login_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_ip', sa.String(length=64), nullable=True),
    sa.Column('preferences', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email'),
    sa.UniqueConstraint('google_sub')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_deleted_at'), ['deleted_at'], unique=False)

    op.create_table('webhook_events',
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('event_id', sa.String(length=160), nullable=False),
    sa.Column('event_type', sa.String(length=80), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'event_id', name='uq_webhook_provider_event')
    )
    op.create_table('admin_sessions',
    sa.Column('admin_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('mfa_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=300), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['admin_users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('admin_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_admin_sessions_admin_id'), ['admin_id'], unique=False)

    op.create_table('workspaces',
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('logo_url', sa.String(length=500), nullable=True),
    sa.Column('brand_color', sa.String(length=9), nullable=True),
    sa.Column('industry', sa.String(length=80), nullable=True),
    sa.Column('company_size', sa.String(length=40), nullable=True),
    sa.Column('website', sa.String(length=300), nullable=True),
    sa.Column('sales_model', sa.String(length=40), nullable=True),
    sa.Column('goals', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('timezone', sa.String(length=64), server_default='Asia/Kolkata', nullable=False),
    sa.Column('currency', sa.String(length=3), server_default='INR', nullable=False),
    sa.Column('locale', sa.String(length=10), server_default='en', nullable=False),
    sa.Column('onboarding_completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('onboarding_state', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.Column('plan_key', sa.String(length=40), server_default='trial', nullable=False),
    sa.Column('subscription_status', sa.String(length=20), server_default='trialing', nullable=False),
    sa.Column('billing_interval', sa.String(length=10), nullable=True),
    sa.Column('trial_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('grace_ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_at_period_end', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('provider_customer_id', sa.String(length=120), nullable=True),
    sa.Column('credit_balance', sa.Integer(), server_default='0', nullable=False),
    sa.Column('limit_overrides', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('trial_milestones_sent', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    with op.batch_alter_table('workspaces', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workspaces_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_workspaces_owner_id'), ['owner_id'], unique=False)

    op.create_table('ai_conversations',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('messages', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_conversations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_conversations_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_conversations_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('ai_usage',
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('feature', sa.String(length=40), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('model', sa.String(length=60), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_usage', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ai_usage_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_ai_usage_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('automations',
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('description', sa.String(length=400), nullable=True),
    sa.Column('trigger_type', sa.String(length=40), nullable=False),
    sa.Column('trigger_config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('graph', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('run_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('automations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_automations_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_automations_trigger_type'), ['trigger_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_automations_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('checkout_sessions',
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('plan_key', sa.String(length=40), nullable=False),
    sa.Column('interval', sa.String(length=10), nullable=False),
    sa.Column('coupon_code', sa.String(length=40), nullable=True),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('provider_session_id', sa.String(length=160), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('checkout_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_checkout_sessions_provider_session_id'), ['provider_session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_checkout_sessions_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('companies',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('website', sa.String(length=300), nullable=True),
    sa.Column('domain', sa.String(length=200), nullable=True),
    sa.Column('industry', sa.String(length=80), nullable=True),
    sa.Column('size', sa.String(length=40), nullable=True),
    sa.Column('location', sa.String(length=160), nullable=True),
    sa.Column('annual_revenue', sa.Numeric(precision=16, scale=2), nullable=True),
    sa.Column('phone', sa.String(length=40), nullable=True),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('tags', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('custom', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_companies_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_companies_domain'), ['domain'], unique=False)
        batch_op.create_index(batch_op.f('ix_companies_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_companies_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('coupon_redemptions',
    sa.Column('coupon_id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['coupon_id'], ['coupons.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('coupon_id', 'workspace_id', name='uq_coupon_ws')
    )
    op.create_table('crm_email_templates',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('subject', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('crm_email_templates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_crm_email_templates_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('custom_field_defs',
    sa.Column('entity_type', sa.String(length=20), nullable=False),
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('label', sa.String(length=100), nullable=False),
    sa.Column('field_type', sa.String(length=20), nullable=False),
    sa.Column('options', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('required', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'entity_type', 'key', name='uq_cf_ws_entity_key')
    )
    with op.batch_alter_table('custom_field_defs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_custom_field_defs_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('duplicate_dismissals',
    sa.Column('entity_type', sa.String(length=20), nullable=False),
    sa.Column('a_id', sa.UUID(), nullable=False),
    sa.Column('b_id', sa.UUID(), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'entity_type', 'a_id', 'b_id', name='uq_dup_pair')
    )
    with op.batch_alter_table('duplicate_dismissals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_duplicate_dismissals_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('impersonation_grants',
    sa.Column('admin_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('reason', sa.String(length=300), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['admin_users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code_hash')
    )
    op.create_table('import_jobs',
    sa.Column('entity_type', sa.String(length=20), nullable=False),
    sa.Column('filename', sa.String(length=300), nullable=True),
    sa.Column('status', sa.String(length=15), nullable=False),
    sa.Column('total_rows', sa.Integer(), nullable=False),
    sa.Column('created_count', sa.Integer(), nullable=False),
    sa.Column('skipped_count', sa.Integer(), nullable=False),
    sa.Column('error_count', sa.Integer(), nullable=False),
    sa.Column('mapping', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('import_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_import_jobs_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('integrations',
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('mode', sa.String(length=15), nullable=False),
    sa.Column('account_label', sa.String(length=200), nullable=True),
    sa.Column('credentials_enc', sa.Text(), nullable=True),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.String(length=400), nullable=True),
    sa.Column('connected_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['connected_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'provider', name='uq_integration_ws_provider')
    )
    with op.batch_alter_table('integrations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_integrations_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('leads',
    sa.Column('first_name', sa.String(length=100), nullable=False),
    sa.Column('last_name', sa.String(length=100), nullable=True),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('phone', sa.String(length=40), nullable=True),
    sa.Column('company_name', sa.String(length=200), nullable=True),
    sa.Column('job_title', sa.String(length=120), nullable=True),
    sa.Column('source', sa.String(length=60), nullable=True),
    sa.Column('status', sa.String(length=30), server_default='new', nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('score', sa.Integer(), server_default='0', nullable=False),
    sa.Column('score_reasons', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('tags', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('location', sa.String(length=160), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('custom', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('last_contacted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('next_follow_up_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('converted_contact_id', sa.UUID(), nullable=True),
    sa.Column('converted_deal_id', sa.UUID(), nullable=True),
    sa.Column('lost_reason', sa.String(length=200), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_leads_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_leads_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_leads_next_follow_up_at'), ['next_follow_up_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_leads_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_leads_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_leads_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('notifications',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.String(length=500), nullable=True),
    sa.Column('link', sa.String(length=300), nullable=True),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notifications_user_id'), ['user_id'], unique=False)
        batch_op.create_index('ix_notifications_user_unread', ['user_id', 'read_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('pipelines',
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('is_default', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.Column('currency', sa.String(length=3), server_default='INR', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pipelines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pipelines_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_pipelines_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('roles',
    sa.Column('workspace_id', sa.UUID(), nullable=True),
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=True),
    sa.Column('permissions', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('is_system', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('rank', sa.Integer(), server_default='0', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'key', name='uq_roles_ws_key')
    )
    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_roles_workspace_id'), ['workspace_id'], unique=False)
        batch_op.create_index('uq_roles_system_key', ['key'], unique=True, postgresql_where=sa.text('workspace_id IS NULL'))

    op.create_table('saved_reports',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('report_type', sa.String(length=40), nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('schedule', sa.String(length=15), nullable=True),
    sa.Column('recipients', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('last_sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('saved_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_saved_reports_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('saved_views',
    sa.Column('entity_type', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('shared', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('sort', sa.String(length=60), nullable=True),
    sa.Column('columns', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('saved_views', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_saved_views_entity_type'), ['entity_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_saved_views_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('subscriptions',
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('plan_key', sa.String(length=40), nullable=False),
    sa.Column('interval', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('coupon_code', sa.String(length=40), nullable=True),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('provider_subscription_id', sa.String(length=120), nullable=True),
    sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_at_period_end', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('pending_plan_key', sa.String(length=40), nullable=True),
    sa.Column('pending_interval', sa.String(length=10), nullable=True),
    sa.Column('payment_method', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subscriptions_provider_subscription_id'), ['provider_subscription_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_subscriptions_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('tags',
    sa.Column('name', sa.String(length=40), nullable=False),
    sa.Column('color', sa.String(length=9), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'name', name='uq_tag_ws_name')
    )
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tags_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('teams',
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('teams', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_teams_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('user_sessions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=True),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('family_id', sa.UUID(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=300), nullable=True),
    sa.Column('impersonator_admin_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_sessions_family_id'), ['family_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_sessions_user_id'), ['user_id'], unique=False)

    op.create_table('automation_runs',
    sa.Column('automation_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=15), nullable=False),
    sa.Column('trigger_payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('cursor_node_id', sa.String(length=60), nullable=True),
    sa.Column('resume_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['automation_id'], ['automations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('automation_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_automation_runs_automation_id'), ['automation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_automation_runs_resume_at'), ['resume_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_automation_runs_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_automation_runs_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('contacts',
    sa.Column('first_name', sa.String(length=100), nullable=False),
    sa.Column('last_name', sa.String(length=100), nullable=True),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('phone', sa.String(length=40), nullable=True),
    sa.Column('job_title', sa.String(length=120), nullable=True),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('avatar_url', sa.String(length=500), nullable=True),
    sa.Column('location', sa.String(length=160), nullable=True),
    sa.Column('socials', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('tags', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('custom', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('source_lead_id', sa.UUID(), nullable=True),
    sa.Column('last_contacted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('unsubscribed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('contacts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_contacts_company_id'), ['company_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_contacts_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_contacts_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_contacts_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_contacts_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('invitations',
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('invited_by', sa.UUID(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('invitations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invitations_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('payments',
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('subscription_id', sa.UUID(), nullable=True),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('provider_payment_id', sa.String(length=120), nullable=True),
    sa.Column('failure_reason', sa.String(length=300), nullable=True),
    sa.Column('refunded_amount', sa.Integer(), server_default='0', nullable=False),
    sa.Column('description', sa.String(length=200), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payments_provider_payment_id'), ['provider_payment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('pipeline_stages',
    sa.Column('pipeline_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('probability', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=10), server_default='open', nullable=False),
    sa.Column('color', sa.String(length=9), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['pipeline_id'], ['pipelines.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('pipeline_stages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pipeline_stages_pipeline_id'), ['pipeline_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pipeline_stages_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('workspace_members',
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('team_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    sa.Column('notification_prefs', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'user_id', name='uq_member_ws_user')
    )
    with op.batch_alter_table('workspace_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workspace_members_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_workspace_members_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('deals',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('contact_id', sa.UUID(), nullable=True),
    sa.Column('lead_id', sa.UUID(), nullable=True),
    sa.Column('pipeline_id', sa.UUID(), nullable=False),
    sa.Column('stage_id', sa.UUID(), nullable=False),
    sa.Column('value', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('currency', sa.String(length=3), server_default='INR', nullable=False),
    sa.Column('probability', sa.Integer(), server_default='0', nullable=False),
    sa.Column('priority', sa.String(length=10), server_default='medium', nullable=False),
    sa.Column('expected_close_date', sa.Date(), nullable=True),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('source', sa.String(length=60), nullable=True),
    sa.Column('tags', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('custom', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='open', nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lost_reason', sa.String(length=200), nullable=True),
    sa.Column('stage_entered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('position', sa.Numeric(precision=20, scale=6), server_default='0', nullable=False),
    sa.Column('lead_score', sa.Integer(), server_default='0', nullable=False),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['pipeline_id'], ['pipelines.id'], ),
    sa.ForeignKeyConstraint(['stage_id'], ['pipeline_stages.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('deals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_deals_closed_at'), ['closed_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_deals_company_id'), ['company_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_deals_contact_id'), ['contact_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_deals_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_deals_expected_close_date'), ['expected_close_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_deals_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_deals_pipeline_id'), ['pipeline_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_deals_stage_id'), ['stage_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_deals_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_deals_workspace_id'), ['workspace_id'], unique=False)
        batch_op.create_index('ix_deals_ws_stage_pos', ['workspace_id', 'stage_id', 'position'], unique=False)

    op.create_table('invoices',
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('payment_id', sa.UUID(), nullable=True),
    sa.Column('number', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('subtotal', sa.Integer(), nullable=False),
    sa.Column('discount', sa.Integer(), nullable=False),
    sa.Column('tax', sa.Integer(), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('line_items', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('period_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('period_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('billing_details', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('number')
    )
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invoices_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('activities',
    sa.Column('type', sa.String(length=30), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('lead_id', sa.UUID(), nullable=True),
    sa.Column('contact_id', sa.UUID(), nullable=True),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('deal_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('activities', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_activities_company_id'), ['company_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_activities_contact_id'), ['contact_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_activities_deal_id'), ['deal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_activities_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_activities_occurred_at'), ['occurred_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_activities_type'), ['type'], unique=False)
        batch_op.create_index(batch_op.f('ix_activities_workspace_id'), ['workspace_id'], unique=False)
        batch_op.create_index('ix_activities_ws_occurred', ['workspace_id', sa.literal_column('occurred_at DESC')], unique=False)

    op.create_table('calls',
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=15), nullable=False),
    sa.Column('outcome', sa.String(length=30), nullable=True),
    sa.Column('phone', sa.String(length=40), nullable=True),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_seconds', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('provider', sa.String(length=30), nullable=True),
    sa.Column('provider_call_id', sa.String(length=120), nullable=True),
    sa.Column('recording_url', sa.String(length=500), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lead_id', sa.UUID(), nullable=True),
    sa.Column('contact_id', sa.UUID(), nullable=True),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('deal_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('calls', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_calls_company_id'), ['company_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_calls_contact_id'), ['contact_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_calls_deal_id'), ['deal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_calls_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_calls_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_calls_scheduled_at'), ['scheduled_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_calls_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('emails',
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=15), nullable=False),
    sa.Column('subject', sa.String(length=500), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('from_address', sa.String(length=254), nullable=True),
    sa.Column('to_addresses', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('cc_addresses', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tracking_id', sa.String(length=40), nullable=True),
    sa.Column('opens', sa.Integer(), server_default='0', nullable=False),
    sa.Column('clicks', sa.Integer(), server_default='0', nullable=False),
    sa.Column('first_opened_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('thread_id', sa.String(length=120), nullable=True),
    sa.Column('provider', sa.String(length=30), nullable=True),
    sa.Column('provider_message_id', sa.String(length=300), nullable=True),
    sa.Column('attachment_file_ids', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('error', sa.String(length=300), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lead_id', sa.UUID(), nullable=True),
    sa.Column('contact_id', sa.UUID(), nullable=True),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('deal_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tracking_id')
    )
    with op.batch_alter_table('emails', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_emails_company_id'), ['company_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_emails_contact_id'), ['contact_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_emails_deal_id'), ['deal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_emails_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_emails_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_emails_scheduled_at'), ['scheduled_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_emails_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_emails_thread_id'), ['thread_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_emails_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('meetings',
    sa.Column('title', sa.String(length=240), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('location', sa.String(length=300), nullable=True),
    sa.Column('meeting_url', sa.String(length=500), nullable=True),
    sa.Column('status', sa.String(length=15), server_default='scheduled', nullable=False),
    sa.Column('attendees', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('organizer_id', sa.UUID(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('external_event_id', sa.String(length=200), nullable=True),
    sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lead_id', sa.UUID(), nullable=True),
    sa.Column('contact_id', sa.UUID(), nullable=True),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('deal_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organizer_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_meetings_company_id'), ['company_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_meetings_contact_id'), ['contact_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_meetings_deal_id'), ['deal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_meetings_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_meetings_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_meetings_starts_at'), ['starts_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_meetings_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('notes',
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('author_id', sa.UUID(), nullable=True),
    sa.Column('pinned', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('mentions', sa.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lead_id', sa.UUID(), nullable=True),
    sa.Column('contact_id', sa.UUID(), nullable=True),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('deal_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notes_company_id'), ['company_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notes_contact_id'), ['contact_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notes_deal_id'), ['deal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notes_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_notes_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notes_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('tasks',
    sa.Column('title', sa.String(length=240), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('assignee_id', sa.UUID(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('priority', sa.String(length=10), server_default='medium', nullable=False),
    sa.Column('status', sa.String(length=15), server_default='todo', nullable=False),
    sa.Column('kind', sa.String(length=20), server_default='task', nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('position', sa.Numeric(precision=20, scale=6), server_default='0', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lead_id', sa.UUID(), nullable=True),
    sa.Column('contact_id', sa.UUID(), nullable=True),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('deal_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tasks_assignee_id'), ['assignee_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_company_id'), ['company_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_contact_id'), ['contact_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_deal_id'), ['deal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_due_at'), ['due_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('files',
    sa.Column('task_id', sa.UUID(), nullable=True),
    sa.Column('filename', sa.String(length=300), nullable=False),
    sa.Column('storage_key', sa.String(length=500), nullable=False),
    sa.Column('mime_type', sa.String(length=120), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('uploaded_by', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=15), server_default='ready', nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lead_id', sa.UUID(), nullable=True),
    sa.Column('contact_id', sa.UUID(), nullable=True),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('deal_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_files_company_id'), ['company_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_files_contact_id'), ['contact_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_files_deal_id'), ['deal_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_files_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_files_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_files_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_files_workspace_id'), ['workspace_id'], unique=False)


    # Fast ILIKE search for the command palette and list search boxes.
    for table, expr in [
        ("leads", "(coalesce(first_name,'') || ' ' || coalesce(last_name,'') || ' ' || coalesce(email,'') || ' ' || coalesce(company_name,''))"),
        ("contacts", "(coalesce(first_name,'') || ' ' || coalesce(last_name,'') || ' ' || coalesce(email,''))"),
        ("companies", "(coalesce(name,'') || ' ' || coalesce(domain,''))"),
        ("deals", "(coalesce(name,''))"),
        ("tasks", "(coalesce(title,''))"),
        ("notes", "(coalesce(body,''))"),
    ]:
        op.execute(f"CREATE INDEX ix_{table}_trgm ON {table} USING gin ({expr} gin_trgm_ops)")


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_files_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_files_task_id'))
        batch_op.drop_index(batch_op.f('ix_files_lead_id'))
        batch_op.drop_index(batch_op.f('ix_files_deleted_at'))
        batch_op.drop_index(batch_op.f('ix_files_deal_id'))
        batch_op.drop_index(batch_op.f('ix_files_contact_id'))
        batch_op.drop_index(batch_op.f('ix_files_company_id'))

    op.drop_table('files')
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tasks_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_status'))
        batch_op.drop_index(batch_op.f('ix_tasks_lead_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_due_at'))
        batch_op.drop_index(batch_op.f('ix_tasks_deleted_at'))
        batch_op.drop_index(batch_op.f('ix_tasks_deal_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_contact_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_company_id'))
        batch_op.drop_index(batch_op.f('ix_tasks_assignee_id'))

    op.drop_table('tasks')
    with op.batch_alter_table('notes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notes_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_notes_lead_id'))
        batch_op.drop_index(batch_op.f('ix_notes_deleted_at'))
        batch_op.drop_index(batch_op.f('ix_notes_deal_id'))
        batch_op.drop_index(batch_op.f('ix_notes_contact_id'))
        batch_op.drop_index(batch_op.f('ix_notes_company_id'))

    op.drop_table('notes')
    with op.batch_alter_table('meetings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_meetings_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_meetings_starts_at'))
        batch_op.drop_index(batch_op.f('ix_meetings_lead_id'))
        batch_op.drop_index(batch_op.f('ix_meetings_deleted_at'))
        batch_op.drop_index(batch_op.f('ix_meetings_deal_id'))
        batch_op.drop_index(batch_op.f('ix_meetings_contact_id'))
        batch_op.drop_index(batch_op.f('ix_meetings_company_id'))

    op.drop_table('meetings')
    with op.batch_alter_table('emails', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_emails_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_emails_thread_id'))
        batch_op.drop_index(batch_op.f('ix_emails_status'))
        batch_op.drop_index(batch_op.f('ix_emails_scheduled_at'))
        batch_op.drop_index(batch_op.f('ix_emails_lead_id'))
        batch_op.drop_index(batch_op.f('ix_emails_deleted_at'))
        batch_op.drop_index(batch_op.f('ix_emails_deal_id'))
        batch_op.drop_index(batch_op.f('ix_emails_contact_id'))
        batch_op.drop_index(batch_op.f('ix_emails_company_id'))

    op.drop_table('emails')
    with op.batch_alter_table('calls', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_calls_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_calls_scheduled_at'))
        batch_op.drop_index(batch_op.f('ix_calls_lead_id'))
        batch_op.drop_index(batch_op.f('ix_calls_deleted_at'))
        batch_op.drop_index(batch_op.f('ix_calls_deal_id'))
        batch_op.drop_index(batch_op.f('ix_calls_contact_id'))
        batch_op.drop_index(batch_op.f('ix_calls_company_id'))

    op.drop_table('calls')
    with op.batch_alter_table('activities', schema=None) as batch_op:
        batch_op.drop_index('ix_activities_ws_occurred')
        batch_op.drop_index(batch_op.f('ix_activities_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_activities_type'))
        batch_op.drop_index(batch_op.f('ix_activities_occurred_at'))
        batch_op.drop_index(batch_op.f('ix_activities_lead_id'))
        batch_op.drop_index(batch_op.f('ix_activities_deal_id'))
        batch_op.drop_index(batch_op.f('ix_activities_contact_id'))
        batch_op.drop_index(batch_op.f('ix_activities_company_id'))

    op.drop_table('activities')
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invoices_workspace_id'))

    op.drop_table('invoices')
    with op.batch_alter_table('deals', schema=None) as batch_op:
        batch_op.drop_index('ix_deals_ws_stage_pos')
        batch_op.drop_index(batch_op.f('ix_deals_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_deals_status'))
        batch_op.drop_index(batch_op.f('ix_deals_stage_id'))
        batch_op.drop_index(batch_op.f('ix_deals_pipeline_id'))
        batch_op.drop_index(batch_op.f('ix_deals_owner_id'))
        batch_op.drop_index(batch_op.f('ix_deals_expected_close_date'))
        batch_op.drop_index(batch_op.f('ix_deals_deleted_at'))
        batch_op.drop_index(batch_op.f('ix_deals_contact_id'))
        batch_op.drop_index(batch_op.f('ix_deals_company_id'))
        batch_op.drop_index(batch_op.f('ix_deals_closed_at'))

    op.drop_table('deals')
    with op.batch_alter_table('workspace_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workspace_members_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_workspace_members_user_id'))

    op.drop_table('workspace_members')
    with op.batch_alter_table('pipeline_stages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pipeline_stages_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_pipeline_stages_pipeline_id'))

    op.drop_table('pipeline_stages')
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payments_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_payments_provider_payment_id'))

    op.drop_table('payments')
    with op.batch_alter_table('invitations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invitations_workspace_id'))

    op.drop_table('invitations')
    with op.batch_alter_table('contacts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_contacts_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_contacts_owner_id'))
        batch_op.drop_index(batch_op.f('ix_contacts_email'))
        batch_op.drop_index(batch_op.f('ix_contacts_deleted_at'))
        batch_op.drop_index(batch_op.f('ix_contacts_company_id'))

    op.drop_table('contacts')
    with op.batch_alter_table('automation_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_automation_runs_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_automation_runs_status'))
        batch_op.drop_index(batch_op.f('ix_automation_runs_resume_at'))
        batch_op.drop_index(batch_op.f('ix_automation_runs_automation_id'))

    op.drop_table('automation_runs')
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_sessions_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_sessions_family_id'))

    op.drop_table('user_sessions')
    with op.batch_alter_table('teams', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_teams_workspace_id'))

    op.drop_table('teams')
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tags_workspace_id'))

    op.drop_table('tags')
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_subscriptions_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_subscriptions_provider_subscription_id'))

    op.drop_table('subscriptions')
    with op.batch_alter_table('saved_views', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_saved_views_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_saved_views_entity_type'))

    op.drop_table('saved_views')
    with op.batch_alter_table('saved_reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_saved_reports_workspace_id'))

    op.drop_table('saved_reports')
    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.drop_index('uq_roles_system_key', postgresql_where=sa.text('workspace_id IS NULL'))
        batch_op.drop_index(batch_op.f('ix_roles_workspace_id'))

    op.drop_table('roles')
    with op.batch_alter_table('pipelines', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pipelines_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_pipelines_deleted_at'))

    op.drop_table('pipelines')
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notifications_workspace_id'))
        batch_op.drop_index('ix_notifications_user_unread')
        batch_op.drop_index(batch_op.f('ix_notifications_user_id'))

    op.drop_table('notifications')
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_leads_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_leads_status'))
        batch_op.drop_index(batch_op.f('ix_leads_owner_id'))
        batch_op.drop_index(batch_op.f('ix_leads_next_follow_up_at'))
        batch_op.drop_index(batch_op.f('ix_leads_email'))
        batch_op.drop_index(batch_op.f('ix_leads_deleted_at'))

    op.drop_table('leads')
    with op.batch_alter_table('integrations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_integrations_workspace_id'))

    op.drop_table('integrations')
    with op.batch_alter_table('import_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_import_jobs_workspace_id'))

    op.drop_table('import_jobs')
    op.drop_table('impersonation_grants')
    with op.batch_alter_table('duplicate_dismissals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_duplicate_dismissals_workspace_id'))

    op.drop_table('duplicate_dismissals')
    with op.batch_alter_table('custom_field_defs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_custom_field_defs_workspace_id'))

    op.drop_table('custom_field_defs')
    with op.batch_alter_table('crm_email_templates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_crm_email_templates_workspace_id'))

    op.drop_table('crm_email_templates')
    op.drop_table('coupon_redemptions')
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_companies_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_companies_owner_id'))
        batch_op.drop_index(batch_op.f('ix_companies_domain'))
        batch_op.drop_index(batch_op.f('ix_companies_deleted_at'))

    op.drop_table('companies')
    with op.batch_alter_table('checkout_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_checkout_sessions_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_checkout_sessions_provider_session_id'))

    op.drop_table('checkout_sessions')
    with op.batch_alter_table('automations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_automations_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_automations_trigger_type'))
        batch_op.drop_index(batch_op.f('ix_automations_deleted_at'))

    op.drop_table('automations')
    with op.batch_alter_table('ai_usage', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_usage_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_ai_usage_created_at'))

    op.drop_table('ai_usage')
    with op.batch_alter_table('ai_conversations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ai_conversations_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_ai_conversations_user_id'))

    op.drop_table('ai_conversations')
    with op.batch_alter_table('workspaces', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workspaces_owner_id'))
        batch_op.drop_index(batch_op.f('ix_workspaces_deleted_at'))

    op.drop_table('workspaces')
    with op.batch_alter_table('admin_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_admin_sessions_admin_id'))

    op.drop_table('admin_sessions')
    op.drop_table('webhook_events')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_deleted_at'))

    op.drop_table('users')
    op.drop_table('platform_settings')
    op.drop_table('platform_email_templates')
    op.drop_table('plans')
    op.drop_table('permissions')
    with op.batch_alter_table('job_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_logs_name'))
        batch_op.drop_index(batch_op.f('ix_job_logs_created_at'))

    op.drop_table('job_logs')
    op.drop_table('feature_flags')
    with op.batch_alter_table('email_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_email_logs_created_at'))

    op.drop_table('email_logs')
    op.drop_table('coupons')
    with op.batch_alter_table('auth_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_auth_events_created_at'))

    op.drop_table('auth_events')
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_logs_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_entity_type'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_created_at'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_actor_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_action'))

    op.drop_table('audit_logs')
    with op.batch_alter_table('api_error_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_error_logs_created_at'))

    op.drop_table('api_error_logs')
    with op.batch_alter_table('analytics_events', schema=None) as batch_op:
        batch_op.drop_index('ix_analytics_name_created')
        batch_op.drop_index(batch_op.f('ix_analytics_events_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_analytics_events_user_id'))
        batch_op.drop_index(batch_op.f('ix_analytics_events_name'))
        batch_op.drop_index(batch_op.f('ix_analytics_events_created_at'))

    op.drop_table('analytics_events')
    op.drop_table('admin_users')
