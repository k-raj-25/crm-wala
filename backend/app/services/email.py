"""Transactional email: template rendering + swappable providers (console | smtp | resend)."""
from __future__ import annotations

import base64
import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

import httpx
from flask import current_app
from jinja2.sandbox import SandboxedEnvironment

from app.extensions import db
from app.models import EmailLog, PlatformEmailTemplate
from app.services.email_templates import DEFAULT_TEMPLATES, LAYOUT

log = logging.getLogger("app.email")
_env = SandboxedEnvironment(autoescape=True)


# (filename, mime type, content)
Attachment = tuple[str, str, bytes]


class EmailProvider(Protocol):
    name: str

    def send(self, to: str, subject: str, html: str, *, from_addr: str, reply_to: str | None = None, attachments: list[Attachment] | None = None) -> str | None: ...


class ConsoleProvider:
    """Dev sink: prints the email to the server log. Nothing leaves the machine."""
    name = "console"

    def send(self, to, subject, html, *, from_addr, reply_to=None, attachments=None):
        log.info("EMAIL to=%s subject=%s attachments=%s\n%s", to, subject, [a[0] for a in attachments or []], html)
        return None


class SmtpProvider:
    name = "smtp"

    def send(self, to, subject, html, *, from_addr, reply_to=None, attachments=None):
        cfg = current_app.config
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = from_addr, to, subject
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content("Please view this email in an HTML-capable client.")
        msg.add_alternative(html, subtype="html")
        add_attachments(msg, attachments)
        if not cfg["SMTP_HOST"]:
            raise RuntimeError("SMTP_HOST is not set")
        # 465 is SSL from the first byte; 587/25 start plain and upgrade with STARTTLS
        if cfg["SMTP_PORT"] == 465:
            conn = smtplib.SMTP_SSL(cfg["SMTP_HOST"], 465, timeout=15)
        else:
            conn = smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15)
        with conn as s:
            if cfg["SMTP_PORT"] != 465:
                s.starttls()
            if cfg["SMTP_USER"]:
                s.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            s.send_message(msg)
        return None


class ResendProvider:
    name = "resend"

    def send(self, to, subject, html, *, from_addr, reply_to=None, attachments=None):
        if not current_app.config["RESEND_API_KEY"]:
            raise RuntimeError("RESEND_API_KEY is not set")
        files = [{"filename": n, "content": base64.b64encode(b).decode()} for n, _, b in attachments or []]
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {current_app.config['RESEND_API_KEY']}"},
            json={"from": from_addr, "to": [to], "subject": subject, "html": html, **({"reply_to": reply_to} if reply_to else {}), **({"attachments": files} if files else {})},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("id")


def add_attachments(msg: EmailMessage, attachments: list[Attachment] | None) -> None:
    for name, mime, content in attachments or []:
        main, _, sub = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(content, maintype=main, subtype=sub or "octet-stream", filename=name)


def get_provider() -> EmailProvider:
    return {"smtp": SmtpProvider, "resend": ResendProvider}.get(current_app.config["EMAIL_PROVIDER"], ConsoleProvider)()


NOT_SET_UP = ("Email sending isn't set up on the server yet, so nothing was sent. "
              "Set EMAIL_PROVIDER to smtp or resend (with its settings) in backend/.env and restart the backend.")


def delivers() -> bool:
    """False when mail only goes to the server log (console provider), so callers can say so instead of claiming it was sent."""
    return get_provider().name != "console" or current_app.testing


def _render(s: str, ctx: dict) -> str:
    return _env.from_string(s).render(**ctx)


def render_template(key: str, ctx: dict) -> tuple[str, str]:
    row = db.session.get(PlatformEmailTemplate, key)
    default = DEFAULT_TEMPLATES[key]
    subject, body = (row.subject, row.body_html) if row else (default["subject"], default["body"])
    content = _render(body, ctx)
    # Layout is trusted; content already rendered+escaped.
    html = LAYOUT.replace("{{ content }}", content)
    return _render(subject, ctx), html


def send_raw(to: str, subject: str, html: str, *, workspace_id=None, template_key: str | None = None,
             reply_to: str | None = None, from_name: str | None = None, attachments: list[Attachment] | None = None,
             raise_errors: bool = False) -> bool:
    """Send one email and log it. Returns False on failure; with raise_errors the failure is re-raised for the caller to report."""
    provider = get_provider()
    status, error = ("sent" if provider.name != "console" else "logged"), None
    from_addr = current_app.config["EMAIL_FROM"]
    if from_name:
        # We can't send *as* a user's own address without their mailbox (SPF/DKIM would fail), so show their name and route replies to them.
        from email.utils import formataddr, parseaddr

        from_addr = formataddr((f"{from_name.replace(chr(34), '').replace(chr(10), ' ')[:60]} via CRM Wala", parseaddr(from_addr)[1]))
    try:
        provider.send(to, subject, html, from_addr=from_addr, reply_to=reply_to, attachments=attachments)
    except Exception as e:  # delivery failure must never break the caller
        status, error = "failed", str(e)[:400]
        log.exception("email send failed")
    db.session.add(EmailLog(workspace_id=workspace_id, to_address=to, template_key=template_key, subject=subject[:300],
                            provider=provider.name, status=status, error=error))
    if error and raise_errors:
        raise RuntimeError(error)
    return status != "failed"


def send_template(key: str, to: str, ctx: dict, *, workspace_id=None) -> bool:
    ctx = {"app_url": current_app.config["WEB_ORIGIN"], "billing_url": current_app.config["WEB_ORIGIN"] + "/app/billing", **ctx}
    subject, html = render_template(key, ctx)
    return send_raw(to, subject, html, workspace_id=workspace_id, template_key=key)


def check_syntax(*templates: str) -> None:
    """Raise if any template string has invalid Jinja syntax (used when admins edit templates)."""
    for t in templates:
        _env.from_string(t)
