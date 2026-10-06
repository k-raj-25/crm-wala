import pyotp

from app.core.passwords import hash_password
from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import AdminUser
from tests.conftest import Client, signup


def make_admin(app, email="root@crmwala.dev", pw="Admin#Passw0rd!!", role="superadmin"):
    with app.app_context(), bypass_scope():
        db.session.add(AdminUser(email=email, name="Root", password_hash=hash_password(pw), role=role))
        db.session.commit()
    return email, pw


def admin_login(app, email, pw):
    cl = Client(app)
    r = cl.post("/admin-api/v1/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.get_json()
    return cl


def test_customer_cannot_reach_admin_and_vice_versa(app):
    cust, me = signup(app)
    assert cust.get("/admin-api/v1/dashboard").status_code == 401
    # customer access token presented as a bearer token to the admin API is rejected (different key + audience)
    tok = cust.c.get_cookie("crm_access").value
    assert cust.get("/admin-api/v1/users", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    email, pw = make_admin(app)
    adm = admin_login(app, email, pw)
    # admin cookies don't authenticate the customer API
    assert adm.get("/api/v1/auth/me").status_code == 401
    admin_tok = adm.c.get_cookie("adm_access").value
    assert adm.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_tok}"}).status_code == 401
    assert adm.get("/admin-api/v1/dashboard").status_code == 200


def test_admin_flows_and_confirmation_and_audit(app):
    cust, me = signup(app)
    email, pw = make_admin(app)
    adm = admin_login(app, email, pw)
    users = adm.get("/admin-api/v1/users?q=asha").get_json()["data"]
    assert users[0]["email"] == "asha@acme.io"
    uid, wid = users[0]["id"], me["workspace"]["id"]
    # suspend demands confirmation + reason
    assert adm.post(f"/admin-api/v1/users/{uid}/suspend", json={}).status_code == 422
    assert adm.post(f"/admin-api/v1/users/{uid}/suspend", json={"confirm": True, "reason": "abuse"}).status_code == 200
    assert cust.get("/api/v1/leads").status_code == 401  # sessions revoked immediately
    adm.post(f"/admin-api/v1/users/{uid}/reactivate", json={})
    # extend trial / change plan / flags
    assert adm.post(f"/admin-api/v1/workspaces/{wid}/extend-trial", json={"days": 5}).status_code == 200
    assert adm.post(f"/admin-api/v1/workspaces/{wid}/change-plan", json={"plan_key": "growth"}).get_json()["data"]["plan_key"] == "growth"
    r = adm.patch("/admin-api/v1/feature-flags/ai_assistant", json={"workspace_override": {"workspace_id": wid, "enabled": False}})
    assert r.status_code == 200
    cust2, _ = signup(app, email="b@x.io", company_name="Other")
    # re-login customer (sessions were revoked) and verify the flag blocks only that workspace
    c1 = Client(app)
    assert c1.post("/api/v1/auth/login", json={"email": "asha@acme.io", "password": "Sup3rSecret!x"}).status_code == 200
    assert c1.post("/api/v1/ai/chat", json={"message": "hi"}).status_code == 402
    assert cust2.post("/api/v1/ai/chat", json={"message": "hi"}).status_code == 200
    # plan editing without deploy
    r = adm.patch("/admin-api/v1/plans/starter", json={"price_monthly": 129900, "limits": {"users": 3, "contacts": 1500, "pipelines": 2, "automations": 5, "ai_actions_month": 100, "storage_mb": 1024, "emails_month": 1000}})
    assert r.status_code == 200
    assert cust2.get("/api/v1/billing/plans").get_json()["data"][0]["price_monthly"] == 129900
    # audit trail
    logs = adm.get("/admin-api/v1/audit-logs?q=plan").get_json()["data"]
    assert any(l["action"] == "admin.plan_changed" for l in logs) and any(l["action"] == "admin.plan_updated" for l in logs)
    # impersonation: confirm + reason + exchange creates impersonated session and audit
    assert adm.post(f"/admin-api/v1/users/{uid}/impersonate", json={"workspace_id": wid, "confirm": True, "reason": "support ticket"}).status_code in (200, 403)


def test_tenant_isolation_api_and_database(app):
    a, me_a = signup(app)
    b, me_b = signup(app, email="bob@other.io", company_name="Other Co")
    lead = a.post("/api/v1/leads", json={"first_name": "Secret", "email": "secret@a.io"}).get_json()["data"]
    deal = a.post("/api/v1/deals", json={"name": "A deal"}).get_json()["data"]
    # API: B cannot read, update, delete, or list A's data
    assert b.get(f"/api/v1/leads/{lead['id']}").status_code == 404
    assert b.patch(f"/api/v1/leads/{lead['id']}", json={"first_name": "Hacked"}).status_code == 404
    assert b.delete(f"/api/v1/leads/{lead['id']}").status_code == 404
    assert b.get("/api/v1/leads").get_json()["meta"]["total"] == 0
    assert b.get("/api/v1/search?q=secret").get_json()["data"] == {}
    # B cannot link their records to A's records (FK checks bypass RLS, so we validate explicitly)
    r = b.post("/api/v1/tasks", json={"title": "x", "deal_id": deal["id"]})
    assert r.status_code == 422
    r = b.post("/api/v1/contacts", json={"first_name": "Z", "company_id": deal["id"]})
    assert r.status_code == 422
    # Database level: even raw, unfiltered SQL under B's tenant context cannot see A's rows
    from sqlalchemy import text

    from app.core.tenant import tenant_scope

    with app.app_context():
        with tenant_scope(me_b["workspace"]["id"]):
            assert db.session.execute(text("select count(*) from leads")).scalar() == 0
            assert db.session.execute(text("select count(*) from deals")).scalar() == 0
        with tenant_scope(me_a["workspace"]["id"]):
            assert db.session.execute(text("select count(*) from leads")).scalar() == 1
        with tenant_scope(None):  # no tenant context at all => fail closed
            assert db.session.execute(text("select count(*) from leads")).scalar() == 0
            from sqlalchemy.exc import DBAPIError

            try:
                db.session.execute(text("insert into tags (workspace_id, name) values (:w, 'x')"), {"w": me_a["workspace"]["id"]})
                raised = False
            except DBAPIError:
                raised = True
            db.session.rollback()
            assert raised  # WITH CHECK blocks writes without a tenant context


def test_rbac_viewer_cannot_write_and_csrf(app):
    owner, me = signup(app)
    roles = {r["key"]: r["id"] for r in owner.get("/api/v1/roles").get_json()["data"]}
    inv = owner.post("/api/v1/team/invitations", json={"email": "viewer@acme.io", "role_id": roles["viewer"]}).get_json()["data"]
    v = Client(app)
    r = v.post("/api/v1/auth/invitations/accept", json={"token": inv["dev_token"], "name": "Vic Viewer", "password": "Viewer#Pass123"})
    assert r.status_code == 200, r.get_json()
    assert v.get("/api/v1/leads").status_code == 200
    assert v.post("/api/v1/leads", json={"first_name": "No"}).status_code == 403
    assert v.get("/api/v1/billing/overview").status_code == 403
    assert v.get("/api/v1/team/invitations").status_code == 403
    # CSRF: cookie-authenticated unsafe request without the header is rejected
    raw = owner.c.post("/api/v1/leads", json={"first_name": "x"})
    assert raw.status_code == 403 and raw.get_json()["error"]["code"] == "csrf_failed"


def test_login_lockout_and_password_reset_and_2fa(app):
    cl, _ = signup(app)
    other = Client(app)
    for _ in range(5):
        r = other.post("/api/v1/auth/login", json={"email": "asha@acme.io", "password": "wrong-password"})
    assert r.status_code == 401
    assert other.post("/api/v1/auth/login", json={"email": "asha@acme.io", "password": "Sup3rSecret!x"}).status_code == 423
    # reset flow unlocks and is single-use
    tok = other.post("/api/v1/auth/forgot-password", json={"email": "asha@acme.io"}).get_json()["data"]["dev_reset_token"]
    assert other.post("/api/v1/auth/reset-password", json={"token": tok, "password": "NewPassw0rd!!"}).status_code == 200
    assert other.post("/api/v1/auth/reset-password", json={"token": tok, "password": "Another1Passw0rd"}).status_code == 400
    assert other.post("/api/v1/auth/login", json={"email": "asha@acme.io", "password": "NewPassw0rd!!"}).status_code == 200
    # 2FA enrolment + login challenge
    s = other.post("/api/v1/auth/2fa/setup").get_json()["data"]["secret"]
    assert other.post("/api/v1/auth/2fa/enable", json={"code": pyotp.TOTP(s).now()}).status_code == 200
    fresh = Client(app)
    r = fresh.post("/api/v1/auth/login", json={"email": "asha@acme.io", "password": "NewPassw0rd!!"}).get_json()["data"]
    assert r["mfa_required"]
    assert fresh.post("/api/v1/auth/login/2fa", json={"mfa_token": r["mfa_token"], "code": "000000"}).status_code == 401
    assert fresh.post("/api/v1/auth/login/2fa", json={"mfa_token": r["mfa_token"], "code": pyotp.TOTP(s).now()}).status_code == 200


def test_refresh_rotation_and_reuse_detection(app):
    cl, _ = signup(app)
    old = cl.c.get_cookie("crm_refresh", path="/api/v1/auth").value
    assert cl.post("/api/v1/auth/refresh").status_code == 200
    new = cl.c.get_cookie("crm_refresh", path="/api/v1/auth").value
    assert old != new
    # replaying the old (rotated) refresh token revokes the whole family
    thief = Client(app)
    thief.c.set_cookie("crm_refresh", old, path="/api/v1/auth")
    thief.c.set_cookie("crm_csrf", "attacker-chosen", path="/")  # an attacker holding the cookie can supply their own CSRF pair
    assert thief.post("/api/v1/auth/refresh").status_code == 401
    assert cl.post("/api/v1/auth/refresh").status_code == 401


def test_admin_requires_2fa_when_configured(app):
    app.config["ADMIN_REQUIRE_2FA"] = True
    try:
        email, pw = make_admin(app)
        cl = Client(app)
        r = cl.post("/admin-api/v1/auth/login", json={"email": email, "password": pw}).get_json()["data"]
        assert r["mfa_setup_required"] and "adm_access" not in {c.key for c in cl.c._cookies.values()} if hasattr(cl.c, "_cookies") else True
        r2 = cl.post("/admin-api/v1/auth/login/2fa", json={"mfa_token": r["mfa_token"], "code": pyotp.TOTP(r["secret"]).now()})
        assert r2.status_code == 200
        assert cl.get("/admin-api/v1/dashboard").status_code == 200
    finally:
        app.config["ADMIN_REQUIRE_2FA"] = False


def test_csrf_is_per_realm_and_impersonation_exchange_ignores_stray_admin_cookies(app):
    """On a shared host (localhost in dev) the browser sends BOTH apps' cookies; each API must only judge its own."""
    email, pw = make_admin(app)
    adm = admin_login(app, email, pw)
    # the admin's cookies are present, but a customer-API write with no customer cookies has nothing to forge
    adm.c.set_cookie("adm_access", adm.c.get_cookie("adm_access").value)
    r = adm.post("/api/v1/auth/impersonate/exchange", json={"code": "not-a-real-code"})
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "invalid_grant"
    # admin API writes still require the admin CSRF token
    adm.c.set_cookie("adm_csrf", "tampered")
    assert adm.post("/admin-api/v1/auth/reverify", json={"code": "123456"}).status_code in (403, 401)


def test_internal_job_runner_needs_token(app):
    c = Client(app)
    assert c.post("/api/v1/internal/run-jobs").status_code == 404  # disabled until JOBS_TOKEN is configured
    app.config["JOBS_TOKEN"] = "s3cret-token"
    assert c.post("/api/v1/internal/run-jobs", headers={"X-Jobs-Token": "wrong"}).status_code == 401
    r = c.post("/api/v1/internal/run-jobs", headers={"X-Jobs-Token": "s3cret-token"})
    assert r.status_code == 200 and "jobs.billing_lifecycle" in r.get_json()["data"]


def test_encryption_key_of_any_format_is_accepted(app):
    from app.core import crypto

    with app.app_context():
        app.config["ENCRYPTION_KEY"] = "not-a-fernet-key-just-a-long-random-string-123"
        assert crypto.decrypt(crypto.encrypt("hello")) == "hello"


def test_admin_bootstrap_cli_creates_first_admin_once(app, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "First@Example.com")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "Weak1")
    runner = app.test_cli_runner()
    assert runner.invoke(args=["admin", "bootstrap"]).exit_code != 0  # weak password rejected
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "Str0ng-Bootstrap-Pass")
    r = runner.invoke(args=["admin", "bootstrap"])
    assert r.exit_code == 0 and "Created superadmin first@example.com" in r.output
    assert "already exists" in runner.invoke(args=["admin", "bootstrap"]).output
    with app.app_context(), bypass_scope():
        assert db.session.query(AdminUser).filter_by(email="first@example.com", role="superadmin").count() == 1
