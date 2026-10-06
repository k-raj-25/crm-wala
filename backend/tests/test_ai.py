import datetime as dt

from tests.conftest import signup


def test_ai_assistant_answers_from_data_and_meters(app):
    cl, _ = signup(app)
    cl.post("/api/v1/leads", json={"first_name": "Old", "last_name": "Lead", "email": "old@corp.io", "job_title": "CEO"})
    pid = cl.get("/api/v1/pipelines").get_json()["data"][0]["id"]
    cl.post("/api/v1/deals", json={"name": "Big Deal", "value": 900000, "expected_close_date": dt.date.today().isoformat()})
    r = cl.post("/api/v1/ai/chat", json={"message": "Show me my highest-value opportunities."}).get_json()["data"]
    assert "Big Deal" in r["answer"]
    r2 = cl.post("/api/v1/ai/chat", json={"message": "Which leads haven't been contacted in 7 days?", "conversation_id": r["conversation_id"]}).get_json()["data"]
    assert "Old Lead" in r2["answer"]
    assert r2["usage"]["used"] == 2
    d = cl.post("/api/v1/ai/email-draft", json={"entity": "lead", "id": cl.get("/api/v1/leads").get_json()["data"][0]["id"], "goal": "intro"}).get_json()["data"]
    assert d["subject"] and "Hi Old" in d["body"]
    assert cl.get("/api/v1/ai/next-best-actions").status_code == 200
    assert cl.get("/api/v1/ai/data-cleanup").status_code == 200
    assert cl.get("/api/v1/ai/pipeline-diagnosis").status_code == 200


def test_ai_limit(app):
    from app.core.tenant import bypass_scope
    from app.extensions import db
    from app.models import Workspace

    cl, me = signup(app)
    with app.app_context(), bypass_scope():
        db.session.get(Workspace, me["workspace"]["id"]).limit_overrides = {"ai_actions_month": 1}
        db.session.commit()
    assert cl.post("/api/v1/ai/chat", json={"message": "hello"}).status_code == 200
    r = cl.post("/api/v1/ai/chat", json={"message": "hello again"})
    assert r.status_code == 402 and r.get_json()["error"]["code"] == "plan_limit_reached"
