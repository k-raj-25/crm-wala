from tests.conftest import SIGNUP, Client, signup


def test_signup_me_and_crud(app):
    cl, me = signup(app)
    assert me["workspace"]["name"] == "Acme Studio"
    assert me["subscription"]["status"] == "trialing"
    assert me["role"]["key"] == "owner"
    r = cl.post("/api/v1/leads", json={"first_name": "John", "last_name": "Smith", "email": "john@example.com", "job_title": "CEO", "source": "referral"})
    assert r.status_code == 201, r.get_json()
    lead = r.get_json()["data"]
    assert lead["score"] > 30
    r = cl.get("/api/v1/leads?q=john")
    assert r.get_json()["meta"]["total"] == 1
    r = cl.post(f"/api/v1/leads/{lead['id']}/convert", json={"create_deal": True, "deal_name": "Acme deal", "deal_value": 50000})
    assert r.status_code == 200, r.get_json()
    ids = r.get_json()["data"]
    r = cl.get("/api/v1/pipelines")
    p = r.get_json()["data"][0]
    r = cl.get(f"/api/v1/pipelines/{p['id']}/board")
    cols = r.get_json()["data"]["columns"]
    assert cols[0]["count"] == 1
    won = next(c for c in cols if c["stage"]["kind"] == "won")
    r = cl.post(f"/api/v1/deals/{ids['deal_id']}/move", json={"stage_id": won["stage"]["id"]})
    assert r.get_json()["data"]["status"] == "won"
    r = cl.get(f"/api/v1/timeline?entity=deal&id={ids['deal_id']}")
    assert len(r.get_json()["data"]) >= 2
    r = cl.get("/api/v1/search?q=john")
    assert "contacts" in r.get_json()["data"]


def test_dashboard_and_reports(app):
    cl, _ = signup(app)
    r = cl.get("/api/v1/dashboard?days=30")
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert set(d["metrics"]) >= {"revenue", "pipeline_value", "deals_won", "conversion_rate", "tasks_due_today"}
    assert 4 <= len(d["revenue_series"]) <= 6  # 30 days => weekly buckets
    for t in ["revenue", "sales", "leads", "conversion", "pipeline", "team_performance", "deal_velocity", "activity", "forecast", "customer_acquisition"]:
        r = cl.get(f"/api/v1/reports/{t}?days=60")
        assert r.status_code == 200, (t, r.get_json())
    assert cl.get("/api/v1/reports/revenue/export.pdf").data[:4] == b"%PDF"
    assert cl.get("/api/v1/reports/revenue/export.csv").status_code == 200


def test_calendar_feed_merges_meetings_tasks_and_followups(app):
    import datetime as dt

    cl, _ = signup(app)
    soon = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).replace(microsecond=0)
    r = cl.post("/api/v1/tasks", json={"title": "Send proposal", "due_at": soon.isoformat(), "priority": "high"})
    assert r.status_code == 201, r.get_json()
    r = cl.post("/api/v1/leads", json={"first_name": "Mina", "last_name": "Rao", "email": "mina@example.com", "next_follow_up_at": (soon + dt.timedelta(hours=3)).isoformat()})
    assert r.status_code == 201, r.get_json()
    frm, to = (soon - dt.timedelta(days=5)).date().isoformat(), (soon + dt.timedelta(days=5)).date().isoformat()
    r = cl.get(f"/api/v1/calendar?from={frm}&to={to}")
    assert r.status_code == 200, r.get_json()
    kinds = {e["kind"] for e in r.get_json()["data"]}
    assert {"task", "follow_up"} <= kinds
    # unbounded ranges are rejected so the feed can never be used to dump everything
    assert cl.get("/api/v1/calendar?from=2020-01-01&to=2030-01-01").status_code == 400
