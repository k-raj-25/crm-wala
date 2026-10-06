from tests.conftest import signup

GRAPH = {
    "nodes": [
        {"id": "t", "type": "trigger", "data": {"trigger_type": "lead.created"}, "position": {"x": 0, "y": 0}},
        {"id": "a1", "type": "action", "data": {"action_type": "add_tag", "config": {"tag": "auto"}}, "position": {"x": 0, "y": 100}},
        {"id": "a2", "type": "action", "data": {"action_type": "create_task", "config": {"title": "Call {{first_name}}", "due_in_days": 1}}, "position": {"x": 0, "y": 200}},
        {"id": "a3", "type": "action", "data": {"action_type": "delay", "config": {"amount": 2, "unit": "days"}}, "position": {"x": 0, "y": 300}},
        {"id": "a4", "type": "action", "data": {"action_type": "create_activity", "config": {"title": "Reminder sent"}}, "position": {"x": 0, "y": 400}},
    ],
    "edges": [{"id": "e1", "source": "t", "target": "a1"}, {"id": "e2", "source": "a1", "target": "a2"}, {"id": "e3", "source": "a2", "target": "a3"}, {"id": "e4", "source": "a3", "target": "a4"}],
}


def test_automation_runs_and_delay_resumes(app):
    import datetime as dt
    from app.core.tenant import bypass_scope
    from app.extensions import db
    from app.models import AutomationRun
    from app.models.base import utcnow
    from app.services.automation import resume_due

    cl, _ = signup(app)
    r = cl.post("/api/v1/automations", json={"name": "Welcome flow", "trigger_type": "lead.created", "graph": GRAPH, "is_active": True})
    assert r.status_code == 201, r.get_json()
    aid = r.get_json()["data"]["id"]
    lead = cl.post("/api/v1/leads", json={"first_name": "Ravi", "email": "ravi@corp.io"}).get_json()["data"]
    assert "auto" in cl.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]["tags"]
    tasks = cl.get(f"/api/v1/tasks?lead_id={lead['id']}").get_json()["data"]
    assert tasks[0]["title"] == "Call Ravi"
    runs = cl.get(f"/api/v1/automations/{aid}/runs").get_json()["data"]
    assert runs[0]["status"] == "waiting"
    with app.app_context(), bypass_scope():
        run = db.session.get(AutomationRun, runs[0]["id"])
        run.resume_at = utcnow() - dt.timedelta(seconds=1)
        db.session.commit()
    with app.app_context():
        assert resume_due() == 1
    runs = cl.get(f"/api/v1/automations/{aid}/runs").get_json()["data"]
    assert runs[0]["status"] == "completed"


def test_automation_validation(app):
    cl, _ = signup(app)
    bad = {"nodes": GRAPH["nodes"][:2], "edges": [{"id": "x", "source": "a1", "target": "t"}, {"id": "y", "source": "t", "target": "a1"}]}
    r = cl.post("/api/v1/automations", json={"name": "Loop", "trigger_type": "lead.created", "graph": bad})
    assert r.status_code == 422
    webhook = {"nodes": [GRAPH["nodes"][0], {"id": "w", "type": "action", "data": {"action_type": "webhook", "config": {"url": "http://127.0.0.1:9/x"}}}], "edges": [{"id": "e", "source": "t", "target": "w"}]}
    aid = cl.post("/api/v1/automations", json={"name": "Hook", "trigger_type": "lead.created", "graph": webhook, "is_active": True}).get_json()["data"]["id"]
    cl.post("/api/v1/leads", json={"first_name": "Z"})
    run = cl.get(f"/api/v1/automations/{aid}/runs").get_json()["data"][0]
    assert run["status"] == "failed" and "public" in run["steps"][0]["detail"]
