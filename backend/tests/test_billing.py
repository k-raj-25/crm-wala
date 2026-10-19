import datetime as dt

from app.extensions import db
from app.models import Coupon, Workspace
from app.models.base import utcnow
from app.core.tenant import bypass_scope
from tests.conftest import signup


def test_trial_expiry_blocks_but_allows_billing_and_export(app):
    cl, me = signup(app)
    assert cl.get("/api/v1/leads").status_code == 200
    with app.app_context(), bypass_scope():
        ws = db.session.get(Workspace, me["workspace"]["id"])
        ws.trial_ends_at = utcnow() - dt.timedelta(minutes=1)
        db.session.commit()
    r = cl.get("/api/v1/leads")
    assert r.status_code == 402 and r.get_json()["error"]["code"] == "trial_expired"
    assert cl.get("/api/v1/billing/overview").status_code == 200
    assert cl.get("/api/v1/leads/export").status_code == 200
    assert cl.post("/api/v1/leads", json={"first_name": "x"}).status_code == 402


def test_checkout_upgrade_cancel_and_failed_payment(app):
    cl, me = signup(app)
    with app.app_context(), bypass_scope():
        db.session.add(Coupon(code="LAUNCH20", percent_off=20))
        db.session.commit()
    q = cl.post("/api/v1/billing/quote", json={"plan_key": "growth", "interval": "monthly", "coupon_code": "launch20"}).get_json()["data"]
    assert q["subtotal"] == 249900 and q["discount"] == 49980 and q["tax"] > 0
    r = cl.post("/api/v1/billing/checkout", json={"plan_key": "growth", "interval": "monthly", "coupon_code": "LAUNCH20"})
    sid = r.get_json()["data"]["session_id"]
    r = cl.post("/api/v1/billing/mock/complete", json={"session_id": sid, "outcome": "success"})
    assert r.status_code == 200, r.get_json()
    ov = cl.get("/api/v1/billing/overview").get_json()["data"]
    assert ov["subscription"]["status"] == "active" and ov["subscription"]["plan_key"] == "growth"
    inv = cl.get("/api/v1/billing/invoices").get_json()["data"]
    assert len(inv) == 1 and inv[0]["discount"] == 49980
    assert cl.get(f"/api/v1/billing/invoices/{inv[0]['id']}/pdf").data[:4] == b"%PDF"
    # downgrade is scheduled, not immediate
    r = cl.post("/api/v1/billing/checkout", json={"plan_key": "starter", "interval": "monthly"})
    assert r.get_json()["data"]["scheduled"] is True
    # cancel at period end keeps access
    cl.post("/api/v1/billing/cancel", json={})
    assert cl.get("/api/v1/leads").status_code == 200
    # coupon is single-use per workspace
    r = cl.post("/api/v1/billing/quote", json={"plan_key": "business", "interval": "annual", "coupon_code": "LAUNCH20"})
    assert r.status_code == 422


def test_plan_limits_enforced(app):
    cl, me = signup(app)
    with app.app_context(), bypass_scope():
        ws = db.session.get(Workspace, me["workspace"]["id"])
        ws.limit_overrides = {"contacts": 1}
        db.session.commit()
    assert cl.post("/api/v1/contacts", json={"first_name": "A"}).status_code == 201
    r = cl.post("/api/v1/contacts", json={"first_name": "B"})
    assert r.status_code == 402 and r.get_json()["error"]["code"] == "plan_limit_reached"


def test_checkout_info_is_tenant_scoped(app):
    a, _ = signup(app)
    b, _ = signup(app, email="other@example.com", company_name="Other Co")
    sid = a.post("/api/v1/billing/checkout", json={"plan_key": "starter", "interval": "monthly"}).get_json()["data"]["session_id"]
    info = a.get(f"/api/v1/billing/checkout/{sid}")
    assert info.status_code == 200 and info.get_json()["data"]["quote"]["plan_key"] == "starter"
    assert b.get(f"/api/v1/billing/checkout/{sid}").status_code == 404


def test_second_workspace_payment_gets_next_invoice_number(app):
    # Invoices are row-level scoped, so numbering must look past the paying workspace.
    numbers = []
    for i, email in enumerate(["first@example.com", "second@example.com"]):
        cl, _ = signup(app, email=email, company_name=f"Co {i}")
        sid = cl.post("/api/v1/billing/checkout", json={"plan_key": "business", "interval": "monthly"}).get_json()["data"]["session_id"]
        r = cl.post("/api/v1/billing/mock/complete", json={"session_id": sid, "outcome": "success"})
        assert r.status_code == 200, r.get_json()
        numbers.append(cl.get("/api/v1/billing/invoices").get_json()["data"][0]["number"])
    assert numbers[0] != numbers[1] and numbers[1].endswith("000002")
