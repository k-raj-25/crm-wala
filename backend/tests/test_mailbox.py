import uuid

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import Integration, User, Workspace
from app.models.base import utcnow
from app.services import mailbox
from tests.conftest import signup


def _verify(app, email):
    with app.app_context(), bypass_scope():
        db.session.query(User).filter_by(email=email).update({"email_verified_at": utcnow()})
        db.session.commit()


def test_sending_requires_a_verified_email(app):
    cl, me = signup(app)
    assert me["user"]["email_verified"] is False
    r = cl.post("/api/v1/emails/send", json={"to": ["client@example.com"], "subject": "Hello", "body": "Hi"})
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "email_not_verified"
    assert cl.get("/api/v1/emails/sender").get_json()["data"]["verified"] is False
    _verify(app, me["user"]["email"])
    r = cl.post("/api/v1/emails/send", json={"to": ["client@example.com"], "subject": "Hello", "body": "Hi"})
    assert r.status_code == 201, r.get_json()


def test_platform_path_uses_senders_name_and_reply_to(app, monkeypatch):
    cl, me = signup(app)
    _verify(app, me["user"]["email"])
    sent = {}

    def fake_send(self, to, subject, html, *, from_addr, reply_to=None):
        sent.update(to=to, from_addr=from_addr, reply_to=reply_to)

    from app.services.email import ConsoleProvider

    monkeypatch.setattr(ConsoleProvider, "send", fake_send)
    r = cl.post("/api/v1/emails/send", json={"to": ["client@example.com"], "subject": "Hello", "body": "Hi"})
    assert r.status_code == 201
    assert sent["reply_to"] == me["user"]["email"]
    assert sent["from_addr"].startswith(f"{me['user']['name']} via CRM Wala <")
    info = cl.get("/api/v1/emails/sender").get_json()["data"]
    assert info["mode"] == "platform" and info["address"] == me["user"]["email"] and info["verified"] is True


def test_a_users_mailbox_is_never_used_for_a_teammates_email(app):
    cl, me = signup(app)
    with app.app_context(), bypass_scope():
        ws = db.session.query(Workspace).one()
        owner = db.session.query(User).filter_by(email=me["user"]["email"]).one()
        teammate = User(name="Team Mate", email="mate@example.com", password_hash="x")
        db.session.add(teammate)
        db.session.flush()
        db.session.add(Integration(workspace_id=ws.id, provider="gmail", status="connected", mode="live", connected_by=owner.id, account_label=owner.email))
        db.session.commit()
        from flask import g

        with app.test_request_context():
            g.workspace = ws
            assert mailbox._mailbox_integration(ws.id, owner.id) is not None
            assert mailbox._mailbox_integration(ws.id, teammate.id) is None  # the teammate must NOT send through the owner's Gmail
    with app.app_context(), bypass_scope():
        ws = db.session.query(Workspace).one()
        teammate = db.session.query(User).filter_by(email="mate@example.com").one()
        # both can hold their own connection to the same provider in one workspace
        db.session.add(Integration(workspace_id=ws.id, provider="gmail", status="connected", mode="live", connected_by=teammate.id, account_label=teammate.email))
        db.session.commit()
        assert db.session.query(Integration).filter_by(workspace_id=ws.id, provider="gmail").count() == 2


def test_connecting_gmail_is_per_user_in_the_integrations_list(app):
    cl, me = signup(app)
    r = cl.post("/api/v1/integrations/gmail/connect", json={})
    assert r.status_code == 200, r.get_json()
    rows = {i["provider"]: i for i in cl.get("/api/v1/integrations").get_json()["data"]["integrations"]}
    assert rows["gmail"]["status"] == "connected"
    cl.post("/api/v1/integrations/gmail/disconnect", json={})
    rows = {i["provider"]: i for i in cl.get("/api/v1/integrations").get_json()["data"]["integrations"]}
    assert rows["gmail"]["status"] == "not_connected"
