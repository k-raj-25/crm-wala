"""Feature keys that can be gated by plan and toggled by Super Admin feature flags."""
FEATURES: dict[str, str] = {
    "ai_assistant": "AI Assistant",
    "ai_insights": "AI Insights",
    "advanced_reports": "Advanced Reports",
    "automation_builder": "Automation Builder",
    "whatsapp_integration": "WhatsApp integration",
    "email_tracking": "Email tracking",
    "custom_fields": "Custom fields",
    "advanced_permissions": "Advanced permissions",
}

ALL_FEATURES = list(FEATURES)

DEFAULT_PLANS = [
    dict(
        key="trial", name="Free Trial", tagline="Everything, free for 3 days", price_monthly=0, price_annual=0,
        is_trial=True, is_public=False, sort_order=0,
        limits=dict(users=10, contacts=10000, pipelines=None, automations=25, ai_actions_month=100, storage_mb=1024, emails_month=1000),
        features=ALL_FEATURES,
        highlights=["All major features", "No credit card required"],
    ),
    dict(
        key="starter", name="Starter", tagline="For individuals and small businesses", price_monthly=99900,
        price_annual=999000, sort_order=1,
        limits=dict(users=2, contacts=1000, pipelines=2, automations=5, ai_actions_month=100, storage_mb=1024, emails_month=1000),
        features=["ai_assistant", "custom_fields", "automation_builder"],
        highlights=["2 team members", "1,000 contacts", "2 pipelines", "5 automations", "100 AI actions / month"],
    ),
    dict(
        key="growth", name="Growth", tagline="For growing sales teams", price_monthly=249900, price_annual=2499000,
        sort_order=2,
        limits=dict(users=10, contacts=10000, pipelines=None, automations=25, ai_actions_month=500, storage_mb=10240, emails_month=10000),
        features=["ai_assistant", "ai_insights", "custom_fields", "advanced_reports", "automation_builder", "email_tracking"],
        highlights=["10 team members", "10,000 contacts", "Unlimited pipelines", "25 automations", "Advanced reports", "500 AI actions / month"],
    ),
    dict(
        key="business", name="Business", tagline="For larger teams that need control", price_monthly=599900,
        price_annual=5999000, sort_order=3,
        limits=dict(users=50, contacts=100000, pipelines=None, automations=None, ai_actions_month=None, storage_mb=102400, emails_month=100000),
        features=ALL_FEATURES,
        highlights=["50 team members", "100,000 contacts", "Unlimited automations", "Advanced permissions", "WhatsApp", "Fair-use AI"],
    ),
    dict(
        key="enterprise", name="Enterprise", tagline="Custom limits, SSO and dedicated support", price_monthly=None,
        price_annual=None, is_custom=True, sort_order=4,
        limits=dict(users=None, contacts=None, pipelines=None, automations=None, ai_actions_month=None, storage_mb=None, emails_month=None),
        features=ALL_FEATURES,
        highlights=["Unlimited everything", "Custom contract & invoicing", "Priority support"],
    ),
]

DEFAULT_FLAGS = [(k, v, f"Controls access to {v}.") for k, v in FEATURES.items()]

DEFAULT_PLATFORM_SETTINGS = {
    "trial_days": ({"value": 3}, "Length of the free trial in days"),
    "grace_days": ({"value": 3}, "Days of access after a failed payment before the workspace is restricted"),
    "tax": ({"name": "GST", "percent": 18}, "Tax applied to invoices"),
    "annual_months_charged": ({"value": 10}, "Informational: months charged on annual plans"),
    "signups_enabled": ({"value": True}, "Allow new signups"),
    "maintenance_mode": ({"value": False}, "Read-only maintenance banner"),
}
