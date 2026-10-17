import datetime as dt

from tests.conftest import signup
from tests.test_phone_privacy import _member


def _me(cl):
    return cl.get("/api/v1/auth/me").get_json()["data"]["user"]["id"]


def _visit(cl, lead_id, days_ago):
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)
    r = cl.post("/api/v1/meetings", json={"title": "Site visit", "kind": "site_visit", "lead_id": lead_id, "starts_at": start.isoformat(),
                                          "ends_at": (start + dt.timedelta(hours=1)).isoformat()})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def test_only_owner_and_admin_see_the_radar(app):
    owner, _ = signup(app)
    rep = _member(app, owner, "sales_rep", "rep@acme.io")
    mgr = _member(app, owner, "manager", "mgr@acme.io")
    assert owner.get("/api/v1/radar").status_code == 200
    assert rep.get("/api/v1/radar").status_code == 403
    assert mgr.get("/api/v1/radar").status_code == 403
    assert owner.get("/api/v1/radar?days=12").status_code == 400
    types = [p["type"] for p in rep.get("/api/v1/me/notification-preferences").get_json()["data"]]
    assert "leakage_report" not in types
    assert "leakage_report" in [p["type"] for p in owner.get("/api/v1/me/notification-preferences").get_json()["data"]]


def test_lost_lead_that_comes_back_through_a_broker(app):
    owner, _ = signup(app)
    rep = _member(app, owner, "sales_rep", "rep@acme.io")
    rep_id = _me(rep)
    lead = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "phone": "+91 98765 43210", "owner_id": rep_id}).get_json()["data"]
    other = owner.post("/api/v1/leads", json={"first_name": "Untouched", "phone": "+91 90000 11111"}).get_json()["data"]
    assert rep.patch(f"/api/v1/leads/{lead['id']}", json={"status": "lost"}).status_code == 200
    back = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "last_name": "D", "phone": "98765-43210", "source": "broker"}).get_json()["data"]
    owner.post("/api/v1/leads", json={"first_name": "Someone", "phone": "+91 90000 11111"})  # the matching lead was never lost

    r = owner.get("/api/v1/radar").get_json()["data"]
    assert len(r["lost_came_back"]) == 1
    x = r["lost_came_back"][0]
    assert x["lost"]["id"] == lead["id"] and x["lost"]["marked_by"]["name"] == "Rep"
    assert x["back"]["id"] == back["id"] and x["back"]["source"] == "broker" and x["backdoor"] is True and x["matched_on"] == "phone"
    assert "43210" not in str(r)  # no phone numbers in the radar
    assert other["id"] not in str(r)
    assert r["summary"]["lost_came_back"] == 1 and r["summary"]["via_backdoor"] == 1


def test_member_revealing_far_more_numbers_than_the_team(app):
    owner, _ = signup(app)
    big = _member(app, owner, "manager", "big@acme.io")
    small = _member(app, owner, "manager", "small@acme.io")
    leads = [owner.post("/api/v1/leads", json={"first_name": f"Client {i}", "phone": f"+91 98765 4321{i}"}).get_json()["data"] for i in range(6)]
    for lead in leads:
        assert big.post(f"/api/v1/leads/{lead['id']}/reveal-phone", json={}).status_code == 200
    small.post(f"/api/v1/leads/{leads[0]['id']}/reveal-phone", json={})

    rows = owner.get("/api/v1/radar").get_json()["data"]["reveals"]
    assert [(x["user"]["name"], x["reveals"], x["flagged"]) for x in rows] == [("Big", 6, True), ("Small", 1, False)]
    assert rows[0]["not_their_clients"] == 6 and rows[0]["team_usual"] == 1 and rows[0]["times_usual"] == 6


def test_rep_whose_visited_leads_go_cold(app):
    owner, _ = signup(app)
    cold = _member(app, owner, "sales_rep", "cold@acme.io")
    warm = _member(app, owner, "sales_rep", "warm@acme.io")
    cold_leads = [cold.post("/api/v1/leads", json={"first_name": f"Cold {i}"}).get_json()["data"] for i in range(3)]
    warm_leads = [warm.post("/api/v1/leads", json={"first_name": f"Warm {i}"}).get_json()["data"] for i in range(3)]
    for lead in cold_leads:
        _visit(cold, lead["id"], 20)
    for lead in warm_leads:
        _visit(warm, lead["id"], 20)
    _visit(cold, cold_leads[0]["id"], 2)  # too recent to judge, ignored

    with app.app_context():
        from app.core.tenant import bypass_scope
        from app.extensions import db
        from app.models import Activity, Lead

        with bypass_scope():
            for lead in warm_leads:
                ld = db.session.get(Lead, lead["id"])
                db.session.add(Activity(workspace_id=ld.workspace_id, type="call", title="Follow-up call", lead_id=ld.id,
                                        occurred_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=17)))
            db.session.commit()

    rows = owner.get("/api/v1/radar").get_json()["data"]["visits"]
    by = {x["user"]["name"]: x for x in rows}
    assert by["Cold"]["visits"] == 3 and by["Cold"]["cold"] == 3 and by["Cold"]["flagged"] is True and by["Cold"]["team_cold_rate"] == 0
    assert by["Warm"]["cold"] == 0 and by["Warm"]["flagged"] is False
    assert {e["who"]["name"] for e in by["Cold"]["examples"]} == {"Cold 0", "Cold 1", "Cold 2"}


def test_weekly_report_goes_to_the_owner_once(app):
    owner, _ = signup(app)
    rep = _member(app, owner, "sales_rep", "rep@acme.io")
    lead = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "email": "jas@example.com", "owner_id": _me(rep)}).get_json()["data"]
    rep.patch(f"/api/v1/leads/{lead['id']}", json={"status": "unqualified"})
    owner.post("/api/v1/leads", json={"first_name": "Jasmine", "email": "JAS@example.com", "source": "walk_in"})

    from app.jobs.tasks import send_leakage_reports

    with app.app_context():
        assert send_leakage_reports()["sent"] == 1
        assert send_leakage_reports()["sent"] == 0  # once a week

    notes = owner.get("/api/v1/notifications").get_json()["data"]
    n = [x for x in notes if x["type"] == "leakage_report"]
    assert len(n) == 1 and n[0]["link"] == "/app/radar" and "came back" in n[0]["body"]
    assert not [x for x in rep.get("/api/v1/notifications").get_json()["data"] if x["type"] == "leakage_report"]

    s = owner.put("/api/v1/radar/settings", json={"weekly_report": False}).get_json()["data"]
    assert s["weekly_report"] is False and s["last_sent_at"]
    assert owner.get("/api/v1/radar").get_json()["data"]["settings"]["weekly_report"] is False
