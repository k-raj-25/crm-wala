"""Built-in transactional templates. Super Admin can override any of them (stored in platform_email_templates)."""
from __future__ import annotations

DEFAULT_TEMPLATES: dict[str, dict] = {
    "welcome": dict(
        name="Welcome", subject="Welcome to CRM Wala, {{ name }} 👋", variables=["name", "workspace", "app_url"],
        body="<h1>Welcome, {{ name }}!</h1><p>Your workspace <strong>{{ workspace }}</strong> is ready. Your 3-day free trial has started — "
             "everything is unlocked.</p><p><a class='btn' href='{{ app_url }}'>Open your dashboard</a></p>"
             "<p>Tip: create your first lead and move it through the pipeline to see your revenue dashboard come alive.</p>",
    ),
    "verify_email": dict(
        name="Verify email", subject="Verify your email address", variables=["name", "verify_url"],
        body="<h1>Confirm your email</h1><p>Hi {{ name }}, please confirm your email address to secure your account.</p>"
             "<p><a class='btn' href='{{ verify_url }}'>Verify email</a></p><p class='muted'>This link expires in 24 hours.</p>",
    ),
    "password_reset": dict(
        name="Password reset", subject="Reset your password", variables=["name", "reset_url"],
        body="<h1>Reset your password</h1><p>Hi {{ name }}, we received a request to reset your password.</p>"
             "<p><a class='btn' href='{{ reset_url }}'>Choose a new password</a></p>"
             "<p class='muted'>This link expires in 1 hour. If you didn't request this, you can ignore this email.</p>",
    ),
    "trial_started": dict(
        name="Trial started", subject="Your 3-day free trial has started", variables=["name", "workspace", "trial_ends", "app_url"],
        body="<h1>Your trial has started</h1><p>Hi {{ name }}, {{ workspace }} has full access until <strong>{{ trial_ends }}</strong>.</p>"
             "<p><a class='btn' href='{{ app_url }}'>Start exploring</a></p>",
    ),
    "trial_ending": dict(
        name="Trial ending", subject="Your trial ends {{ when }}", variables=["name", "workspace", "when", "billing_url"],
        body="<h1>Your trial ends {{ when }}</h1><p>Hi {{ name }}, choose a plan to keep access to {{ workspace }}. "
             "Your data is safe either way.</p><p><a class='btn' href='{{ billing_url }}'>Choose a plan</a></p>",
    ),
    "trial_expired": dict(
        name="Trial expired", subject="Your trial has ended", variables=["name", "workspace", "billing_url"],
        body="<h1>Your trial has ended</h1><p>Hi {{ name }}, {{ workspace }} is now in read-only recovery mode. "
             "Nothing was deleted — choose a plan to continue, or export your data any time.</p>"
             "<p><a class='btn' href='{{ billing_url }}'>Choose a plan to continue</a></p>",
    ),
    "payment_successful": dict(
        name="Payment successful", subject="Payment received — thank you", variables=["name", "amount", "plan", "invoice_number", "billing_url"],
        body="<h1>Payment received</h1><p>Hi {{ name }}, we received {{ amount }} for the <strong>{{ plan }}</strong> plan "
             "(invoice {{ invoice_number }}).</p><p><a class='btn' href='{{ billing_url }}'>View invoice</a></p>",
    ),
    "payment_failed": dict(
        name="Payment failed", subject="Action needed: payment failed", variables=["name", "workspace", "grace_ends", "billing_url"],
        body="<h1>We couldn't process your payment</h1><p>Hi {{ name }}, the latest payment for {{ workspace }} failed. "
             "You keep full access until <strong>{{ grace_ends }}</strong> while we retry.</p>"
             "<p><a class='btn' href='{{ billing_url }}'>Update payment method</a></p>",
    ),
    "subscription_cancelled": dict(
        name="Subscription cancelled", subject="Your subscription has been cancelled", variables=["name", "workspace", "access_until", "billing_url"],
        body="<h1>Subscription cancelled</h1><p>Hi {{ name }}, {{ workspace }} will keep access until <strong>{{ access_until }}</strong>. "
             "Changed your mind? You can resume any time.</p><p><a class='btn' href='{{ billing_url }}'>Resume subscription</a></p>",
    ),
    "invoice": dict(
        name="Invoice", subject="Invoice {{ invoice_number }}", variables=["name", "invoice_number", "total", "billing_url"],
        body="<h1>Invoice {{ invoice_number }}</h1><p>Hi {{ name }}, your invoice for {{ total }} is available.</p>"
             "<p><a class='btn' href='{{ billing_url }}'>Download invoice</a></p>",
    ),
    "team_invitation": dict(
        name="Team invitation", subject="{{ inviter }} invited you to {{ workspace }}", variables=["inviter", "workspace", "role", "accept_url"],
        body="<h1>You're invited</h1><p>{{ inviter }} invited you to join <strong>{{ workspace }}</strong> as {{ role }}.</p>"
             "<p><a class='btn' href='{{ accept_url }}'>Accept invitation</a></p><p class='muted'>This invitation expires in 7 days.</p>",
    ),
    "meeting_reminder": dict(
        name="Meeting reminder", subject="Reminder: {{ title }} at {{ time }}", variables=["name", "title", "time", "link"],
        body="<h1>{{ title }}</h1><p>Hi {{ name }}, your meeting starts at <strong>{{ time }}</strong>.</p>"
             "<p><a class='btn' href='{{ link }}'>Open in CRM</a></p>",
    ),
    "task_reminder": dict(
        name="Task reminder", subject="Task due: {{ title }}", variables=["name", "title", "due", "link"],
        body="<h1>{{ title }}</h1><p>Hi {{ name }}, this task is due <strong>{{ due }}</strong>.</p>"
             "<p><a class='btn' href='{{ link }}'>Open task</a></p>",
    ),
    "report": dict(
        name="Scheduled report", subject="Your scheduled report: {{ report }}", variables=["report", "summary", "link"],
        body="<h1>{{ report }}</h1><p>{{ summary }}</p><p><a class='btn' href='{{ link }}'>Open report</a></p>",
    ),
}

LAYOUT = """<!doctype html><html><body style="margin:0;background:#f4f5f7;font-family:Inter,Arial,sans-serif;color:#0f172a">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:16px;padding:32px;max-width:560px">
<tr><td><div style="font-weight:700;font-size:18px;margin-bottom:24px">● CRM Wala</div>
<style>h1{font-size:22px;margin:0 0 12px}p{line-height:1.6;color:#334155}.btn{display:inline-block;background:#4f46e5;color:#fff!important;
padding:12px 20px;border-radius:10px;text-decoration:none;font-weight:600}.muted{color:#64748b;font-size:13px}</style>
{{ content }}
</td></tr></table>
<p style="color:#94a3b8;font-size:12px;margin-top:16px">You are receiving this because you have an account on CRM Wala.</p>
</td></tr></table></body></html>"""
