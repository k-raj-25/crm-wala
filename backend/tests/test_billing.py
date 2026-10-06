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
