"""The company's own email account (SMTP), set up once by the workspace owner. Every employee's CRM email goes out through it,
under their own name, with replies going to them. Stored as a workspace-wide Integration row (provider "company_email")."""
from __future__ import annotations

import smtplib
import socket
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from app.extensions import db
from app.models import Integration, User
from app.services import integrations

PROVIDER = "company_email"

# Ready-made server settings, so the owner only types the address and password.
PRESETS: dict[str, dict] = {
    "google": {"label": "Google Workspace / Gmail", "host": "smtp.gmail.com", "port": 587,
               "help": "Use an app password (myaccount.google.com/apppasswords). 2-step verification must be on."},
    "microsoft": {"label": "Microsoft 365 / Outlook", "host": "smtp.office365.com", "port": 587,
                  "help": "Your admin may need to turn on 'Authenticated SMTP' for this mailbox."},
    "zoho": {"label": "Zoho Mail", "host": "smtp.zoho.in", "port": 587, "help": "Use an app-specific password if 2FA is on. Outside India use smtp.zoho.com."},
    "other": {"label": "Other (custom SMTP)", "host": "", "port": 587, "help": "Ask your email host for the SMTP server, port and login."},
}


def get(workspace_id) -> Integration | None:
    return db.session.query(Integration).filter_by(workspace_id=workspace_id, provider=PROVIDER).first()


def active(workspace_id) -> Integration | None:
    i = get(workspace_id)
    return i if i is not None and i.status in ("connected", "error") and i.credentials_enc else None


def view(i: Integration | None) -> dict:
    cfg = dict(i.config or {}) if i else {}
    creds = integrations.get_creds(i) if i is not None and i.credentials_enc else {}
    return {"status": i.status if i else "not_connected", "last_error": i.last_error if i else None,
            "preset": cfg.get("preset", "google"), "host": creds.get("host", ""), "port": creds.get("port", 587),
            "username": creds.get("username", ""), "from_address": cfg.get("from_address", ""), "from_name": cfg.get("from_name", ""),
            "own_address": bool(cfg.get("own_address")), "has_password": bool(creds.get("password")),
            "presets": [{"key": k, **v} for k, v in PRESETS.items()]}


def _domain(addr: str) -> str:
    return parseaddr(addr)[1].rpartition("@")[2].lower()


def from_for(i: Integration, sender: User) -> tuple[str, str | None]:
    """(From header, Reply-To) for an email this person sends. Their own address only when the owner allowed it and it's on the company's domain."""
    cfg = i.config or {}
    company = cfg["from_address"]
    if cfg.get("own_address") and sender.email and _domain(sender.email) == _domain(company):
        return formataddr((sender.name, sender.email)), None
    name = sender.name if not cfg.get("from_name") else f"{sender.name} | {cfg['from_name']}"
    return formataddr((name.replace('"', "").replace("\n", " ")[:80], company)), sender.email


def _connect(creds: dict) -> smtplib.SMTP:
    host, port = creds["host"], int(creds["port"])
    s = smtplib.SMTP_SSL(host, port, timeout=15) if port == 465 else smtplib.SMTP(host, port, timeout=15)
    if port != 465:
        s.starttls()
    s.login(creds["username"], creds["password"])
    return s


def friendly(e: Exception) -> str:
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return "The email server rejected the username or password. For Gmail and Google Workspace, use an app password, not your normal password."
    if isinstance(e, (socket.gaierror, ConnectionRefusedError, TimeoutError, socket.timeout)):
        return "Couldn't reach the email server. Check the server name and port."
    if isinstance(e, smtplib.SMTPSenderRefused):
        return "The email server won't send from this address with this login."
    return f"The email server said: {str(e)[:200]}"


def verify(creds: dict) -> None:
    """Log in once to prove the settings work. Raises ValueError with a message the owner can act on."""
    try:
        with _connect(creds):
            pass
    except Exception as e:
        raise ValueError(friendly(e)) from e


def send(i: Integration, sender: User, to: str, cc: list[str], subject: str, html: str, attachments=None) -> None:
    from app.services.email import add_attachments

    msg = EmailMessage()
    msg["From"], reply_to = from_for(i, sender)
    msg["To"], msg["Subject"] = to, subject
    if cc:
        msg["Cc"] = ", ".join(cc)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content("Please view this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")
    add_attachments(msg, attachments)
    try:
        with _connect(integrations.get_creds(i)) as s:
            s.send_message(msg)
    except Exception as e:
        i.status, i.last_error = "error", friendly(e)
        raise RuntimeError(i.last_error) from e
    if i.status != "connected":
        i.status, i.last_error = "connected", None
