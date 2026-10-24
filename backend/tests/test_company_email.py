import smtplib

import pytest

from app.services import company_email
from tests.test_mailbox import _verify
from tests.test_phone_privacy import _member
from tests.conftest import signup

SETUP = {"preset": "google", "from_address": "sales@acme.io", "password": "app-pass", "from_name": "Acme Homes"}


class FakeSmtp:
    def __init__(self, sent, fail=None):
        self.sent, self.fail = sent, fail

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send_message(self, msg):
        if self.fail:
            raise self.fail
        self.sent.append(msg)


@pytest.fixture()
def smtp(monkeypatch):
    state = {"sent": [], "logins": [], "fail_login": None, "fail_send": None}

    def connect(creds):
        state["logins"].append(creds)
        if state["fail_login"]:
            raise state["fail_login"]
        return FakeSmtp(state["sent"], state["fail_send"])

    monkeypatch.setattr(company_email, "_connect", connect)
    return state


def test_only_the_owner_connects_and_it_logs_in_first(app, smtp):
    owner, _ = signup(app)
    rep = _member(app, owner, "admin", "admin@acme.io")
    assert rep.put("/api/v1/emails/company", json=SETUP).status_code == 403
    smtp["fail_login"] = smtplib.SMTPAuthenticationError(535, b"bad")
    r = owner.put("/api/v1/emails/company", json=SETUP)
    assert r.status_code == 422 and "app password" in r.get_json()["error"]["message"]
    smtp["fail_login"] = None
    r = owner.put("/api/v1/emails/company", json=SETUP)
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert d["status"] == "connected" and d["host"] == "smtp.gmail.com" and d["username"] == "sales@acme.io" and d["has_password"] and "password" not in d
    assert smtp["logins"][-1] == {"host": "smtp.gmail.com", "port": 587, "username": "sales@acme.io", "password": "app-pass"}
    # others only see whether it is set up, never the login
    assert set(rep.get("/api/v1/emails/company").get_json()["data"]) == {"status", "from_address", "own_address"}
    # saving again with a blank password keeps the saved one
    r = owner.put("/api/v1/emails/company", json={**SETUP, "password": ""})
    assert r.status_code == 200, r.get_json()
    assert smtp["logins"][-1]["password"] == "app-pass"


def test_everyones_email_goes_out_through_the_company_account(app, smtp):
    owner, _ = signup(app)
    owner.put("/api/v1/emails/company", json=SETUP)
    rep = _member(app, owner, "sales_rep", "ravi@gmail.com")
    _verify(app, "ravi@gmail.com")
    info = rep.get("/api/v1/emails/sender").get_json()["data"]
    assert info["mode"] == "company" and info["from"] == "Ravi | Acme Homes <sales@acme.io>"
    r = rep.post("/api/v1/emails/send", json={"to": ["client@example.com"], "subject": "Hello", "body": "Hi"})
    assert r.status_code == 201 and r.get_json()["data"]["status"] == "sent"
    msg = smtp["sent"][-1]
    assert msg["From"] == "Ravi | Acme Homes <sales@acme.io>" and msg["Reply-To"] == "ravi@gmail.com" and msg["To"] == "client@example.com"


def test_own_address_only_for_people_on_the_company_domain(app, smtp):
    owner, me = signup(app)
    owner.put("/api/v1/emails/company", json={**SETUP, "own_address": True})
    _verify(app, me["user"]["email"])  # asha@acme.io: same domain
    owner.post("/api/v1/emails/send", json={"to": ["client@example.com"], "subject": "Hello", "body": "Hi"})
    assert smtp["sent"][-1]["From"] == "Asha Rao <asha@acme.io>" and smtp["sent"][-1]["Reply-To"] is None
    rep = _member(app, owner, "sales_rep", "ravi@gmail.com")
    _verify(app, "ravi@gmail.com")
    rep.post("/api/v1/emails/send", json={"to": ["client@example.com"], "subject": "Hello", "body": "Hi"})
    assert smtp["sent"][-1]["From"] == "Ravi | Acme Homes <sales@acme.io>"


def test_a_failed_send_shows_the_reason_and_flags_the_connection(app, smtp):
    owner, me = signup(app)
    owner.put("/api/v1/emails/company", json=SETUP)
    _verify(app, me["user"]["email"])
    smtp["fail_send"] = smtplib.SMTPSenderRefused(553, b"no", "sales@acme.io")
    d = owner.post("/api/v1/emails/send", json={"to": ["client@example.com"], "subject": "Hello", "body": "Hi"}).get_json()["data"]
    assert d["status"] == "failed" and "won't send from this address" in d["error"]
    assert owner.get("/api/v1/emails/company").get_json()["data"]["status"] == "error"
    smtp["fail_send"] = None
    assert owner.post("/api/v1/emails/company/test").status_code == 200
    assert owner.get("/api/v1/emails/company").get_json()["data"]["status"] == "connected"
    assert owner.delete("/api/v1/emails/company").status_code == 200
    assert owner.get("/api/v1/emails/sender").get_json()["data"]["mode"] == "platform"
