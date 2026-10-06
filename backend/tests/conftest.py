from __future__ import annotations

import pytest
from sqlalchemy import text

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.services.workspaces import seed_platform


@pytest.fixture(scope="session")
def app():
    app = create_app(TestConfig)
    with app.app_context():
        from flask_migrate import upgrade

        db.session.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        db.session.commit()
        upgrade(directory="migrations")
        from app.core.tenant import bypass_scope

        with bypass_scope():
            seed_platform()
    return app


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        from app.core.tenant import bypass_scope

        db.session.rollback()
        with bypass_scope():
            db.session.execute(text(
                "TRUNCATE users, workspaces, admin_users, audit_logs, analytics_events, email_logs, auth_events, webhook_events, "
                "coupons, job_logs, api_error_logs CASCADE"))
            db.session.commit()


class Client:
    """Thin wrapper around Flask's test client that mimics the browser: cookies + CSRF header."""

    def __init__(self, app):
        self.c = app.test_client()
        self.app = app

    def _h(self, extra=None):
        h = dict(extra or {})
        csrf = self.c.get_cookie("crm_csrf") or self.c.get_cookie("adm_csrf")
        if csrf:
            h["X-CSRF-Token"] = csrf.value
        return h

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def patch(self, url, json=None, **kw):
        return self.c.patch(url, json=json, headers=self._h(), **kw)

    def put(self, url, json=None, **kw):
        return self.c.put(url, json=json, headers=self._h(), **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self._h(), **kw)


SIGNUP = dict(name="Asha Rao", email="asha@acme.io", password="Sup3rSecret!x", company_name="Acme Studio", company_size="2-10", industry="SaaS", role="Founder")


def signup(app, **over):
    cl = Client(app)
    body = {**SIGNUP, **over}
    r = cl.post("/api/v1/auth/signup", json=body)
    assert r.status_code == 201, r.get_json()
    return cl, r.get_json()["data"]


@pytest.fixture()
def client(app):
    cl, _ = signup(app)
    return cl
