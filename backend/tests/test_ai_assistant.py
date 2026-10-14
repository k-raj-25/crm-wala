"""Bring-your-own-key settings, "do it for me" proposals, and the AI features (basic mode + a faked real provider)."""
import datetime as dt
import json
import re

import httpx

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import AuditLog
from tests.conftest import signup
from tests.test_realestate import _project

PH = re.compile(r"^\{\{([\w.]+)\}\}$")


def _fill(v, values, results):
    if isinstance(v, str):
        m = PH.match(v)
        if m:
            key = m.group(1)
            if key.startswith("result."):
                _, i, field = key.split(".", 2)
                return results[int(i)][field]
            return values[key]
        return re.sub(r"\{\{result\.(\d+)\.(\w+)\}\}", lambda mm: str(results[int(mm.group(1))][mm.group(2)]), v)
    if isinstance(v, dict):
        return {k: _fill(x, values, results) for k, x in v.items()}
    if isinstance(v, list):
        return [_fill(x, values, results) for x in v]
    return v


def approve(cl, p, edits=None):
    """What the browser does when someone presses Approve: fill the edited values into the calls and run them in order."""
    values = {c["key"]: c["to"] for c in p["changes"]} | (edits or {})
    results = []
    for op in p["ops"]:
        r = getattr(cl, op["method"].lower())(op["path"] + "?via=ai", json=_fill(op.get("body"), values, results)) if op["method"] != "DELETE" else cl.delete(op["path"] + "?via=ai")
        assert r.status_code in (200, 201, 204), (op, r.get_json())
        results.append((r.get_json() or {}).get("data") or {})
    return results


def undo(cl, p, results):
    for op in p["undo"] or []:
        path = _fill(op["path"], {}, results)
        r = cl.delete(path) if op["method"] == "DELETE" else getattr(cl, op["method"].lower())(path, json=_fill(op.get("body"), {}, results))
        assert r.status_code in (200, 201, 204), (op, r.get_json())


def _lead(cl, **kw):
    r = cl.post("/api/v1/leads", json={"first_name": "Priya", "last_name": "Sharma", "phone": "9876543210", **kw})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body


def test_byok_settings_are_encrypted_tested_and_scoped(client, monkeypatch):
    s = client.get("/api/v1/ai/settings").get_json()["data"]
    assert s["source"] == "basic" and s["connected"] is False and len(s["providers"]) == 4 and all(s["features"].values())
    seen = []

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        seen.append((url, headers))
        if headers.get("Authorization") == "Bearer sk-bad-key-123":
            return FakeResponse(401, {"error": {"message": "Incorrect API key"}})
        return FakeResponse(200, {"choices": [{"message": {"content": "OK"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}, "model": json["model"]})

    monkeypatch.setattr(httpx, "post", fake_post)
    r = client.put("/api/v1/ai/settings", json={"provider": "openai", "api_key": "sk-bad-key-123"})
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "ai_key_invalid"
    r = client.put("/api/v1/ai/settings", json={"provider": "openai", "api_key": "sk-good-key-9876", "smart_model": "gpt-4.1", "features": {"writer": False},
                                                 "monthly_limit": 500, "mask_pii": True})
    d = r.get_json()["data"]
    assert r.status_code == 200 and d["connected"] and d["key_last4"] == "9876" and d["features"]["writer"] is False and d["monthly_limit"] == 500
    assert "sk-good-key-9876" not in json.dumps(d)
    assert seen[-1][0] == "https://api.openai.com/v1/chat/completions"
    st = client.get("/api/v1/ai/status").get_json()["data"]
    assert st["mode"] == "workspace" and st["provider"] == "openai" and st["audio_files"] is True
    with client.app.app_context(), bypass_scope():
        from app.models import Integration

        row = db.session.query(Integration).filter_by(provider="ai").one()
        assert "sk-good" not in (row.credentials_enc or "")  # stored encrypted
        assert db.session.query(AuditLog).filter_by(action="ai.settings_updated").count() == 2 - 1  # the rejected key saved nothing
    # a switched-off feature refuses politely
    pid, _ = _project(client)
    r = client.post("/api/v1/ai/listing", json={"kind": "whatsapp", "project_id": pid})
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "ai_feature_off"
    # another workspace doesn't see or use this key
    other, _ = signup(client.app, email="other@x.io", company_name="Other Realty")
    assert other.get("/api/v1/ai/status").get_json()["data"]["mode"] == "basic"
    assert client.delete("/api/v1/ai/settings/key").get_json()["data"]["connected"] is False


def test_chat_prepares_changes_that_only_apply_on_approval(client):
    lead = _lead(client, status="contacted")
    r = client.post("/api/v1/ai/chat", json={"message": "Mark this as interested", "page": {"entity": "lead", "id": lead["id"], "label": "Priya Sharma"}}).get_json()["data"]
    assert len(r["proposals"]) == 1
    p = r["proposals"][0]
    assert p["kind"] == "update_lead" and p["changes"][0]["to"] == "qualified" and p["changes"][0]["display_to"] == "Interested"
    assert client.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]["status"] == "contacted"  # nothing saved yet
    res = approve(client, p)
    assert client.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]["status"] == "qualified"
    with client.app.app_context(), bypass_scope():
        row = db.session.query(AuditLog).filter_by(action="lead.updated").order_by(AuditLog.created_at.desc()).first()
        assert row.actor_label.endswith("(via AI assistant)")
    undo(client, p, res)
    assert client.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]["status"] == "contacted"

    t = client.post("/api/v1/ai/chat", json={"message": "Remind me to send the brochure tomorrow"}).get_json()["data"]
    tp = t["proposals"][0]
    assert tp["kind"] == "create_task" and tp["changes"][0]["to"] == "Send the brochure"
    res = approve(client, tp, {"priority": "high"})
    task = client.get("/api/v1/tasks").get_json()["data"][0]
    assert task["title"] == "Send the brochure" and task["priority"] == "high"
    undo(client, tp, res)
    assert client.get("/api/v1/tasks").get_json()["data"] == []
    # requests basic mode can't do are explained, not faked
    msg = client.post("/api/v1/ai/chat", json={"message": "Assign all 99acres leads to Rahul"}).get_json()["data"]
    assert msg["proposals"] == [] and "AI key" in msg["answer"]


def test_real_provider_tool_loop_returns_proposals_and_charts(client, monkeypatch):
    lead = _lead(client, source="99acres", budget_max=15000000)
    _lead(client, first_name="Amit", phone="9811111111", source="99acres", budget_max=9000000)
    with client.app.app_context(), bypass_scope():
        from app.models import Workspace

        ws = db.session.query(Workspace).first()
    me = client.get("/api/v1/auth/me").get_json()["data"]
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        calls.append(json)
        n = len(calls)
        if n == 1:  # the ping when saving the key
            return FakeResponse(200, {"content": [{"type": "text", "text": "OK"}], "usage": {"input_tokens": 1, "output_tokens": 1}})
        if n == 2:
            return FakeResponse(200, {"stop_reason": "tool_use", "usage": {"input_tokens": 50, "output_tokens": 20}, "content": [
                {"type": "tool_use", "id": "t1", "name": "propose_bulk_update_leads", "input": {"filter": {"source": "99acres", "min_budget": 10000000}, "changes": {"owner": "me"}}},
                {"type": "tool_use", "id": "t2", "name": "run_report", "input": {"report": "leads", "days": 30}}]})
        tool_results = json["messages"][-1]["content"]
        assert "awaiting_approval" in tool_results[0]["content"] and "chart" not in tool_results[1]["content"]
        return FakeResponse(200, {"stop_reason": "end_turn", "usage": {"input_tokens": 80, "output_tokens": 30},
                                  "content": [{"type": "text", "text": "I've prepared the reassignment — please review the card."}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert client.put("/api/v1/ai/settings", json={"provider": "anthropic", "api_key": "sk-ant-test-0001"}).status_code == 200
    r = client.post("/api/v1/ai/chat", json={"message": "Give 99acres leads over 1 Cr to me and show leads by source"}).get_json()["data"]
    assert "anthropic" not in r["answer"] and r["charts"][0]["data"]
    p = r["proposals"][0]
    assert p["kind"] == "bulk_update_leads" and [i["name"] for i in p["items"]] == ["Priya Sharma"]
    assert "Now" not in calls[1]["system"] and me["user"]["name"] in calls[1]["system"]
    approve(client, p)
    assert client.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]["owner_id"] == me["user"]["id"]
    assert client.get("/api/v1/ai/settings").get_json()["data"]["usage"]["actions"] >= 1


def test_capture_from_pasted_text_with_duplicate_check(client):
    existing = _lead(client, first_name="Rahul", last_name="Verma", phone="+91 98111 22233")
    text = "Hi, I am Rahul Verma, looking for a 3bhk flat in Sector 62 Noida, budget 1.2 cr to 1.5 cr. Call me on 98111-22233"
    r = client.post("/api/v1/ai/capture", json={"text": text}).get_json()["data"]
    f = r["fields"]
    assert f["bhk"] == "3 BHK" and f["budget_min"] == 12000000 and f["budget_max"] == 15000000 and f["phone"] == "+91 98111 22233" and f["intent"] == "buy"
    assert r["duplicates"][0]["id"] == existing["id"]
    create, update = r["proposals"]
    assert create["kind"] == "create_lead" and "duplicate" in create["warning"].lower()
    approve(client, update)
    got = client.get(f"/api/v1/leads/{existing['id']}").get_json()["data"]
    assert got["bhk"] == "3 BHK" and float(got["budget_max"]) == 15000000
    assert client.post("/api/v1/ai/capture", json={"images": [{"media_type": "image/png", "data": "aGVsbG8gd29ybGQ="}]}).get_json()["error"]["code"] == "ai_key_needed"


def test_visit_log_creates_visit_note_and_follow_up(client):
    pid, tid = _project(client)
    lead = _lead(client, project_id=pid, intent="buy", bhk="3 BHK", budget_max=20000000)
    r = client.post("/api/v1/ai/visit-log", json={"lead_id": lead["id"], "kind": "visit",
                                                    "text": "Showed 301 and 302, liked them, wife will visit Sunday, budget can stretch to 2.2 cr"}).get_json()["data"]
    p = r["proposal"]
    keys = {c["key"] for c in p["changes"]}
    assert {"visit_title", "starts_at", "note", "budget_max", "next_follow_up_at"} <= keys
    assert "Priya" in r["whatsapp_message"]
    res = approve(client, p)
    got = client.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]
    assert float(got["budget_max"]) == 22000000 and got["next_follow_up_at"] and got["last_contacted_at"]
    visits = client.get("/api/v1/meetings", query_string={"lead_id": lead["id"]}).get_json()["data"]
    assert visits[0]["kind"] == "site_visit" and visits[0]["status"] == "completed"
    undo(client, p, res)
    assert client.get("/api/v1/meetings", query_string={"lead_id": lead["id"]}).get_json()["data"] == []


def test_smart_matches_and_reverse_matches(client):
    pid, tid = _project(client, facing="East")
    lead = _lead(client, intent="buy", bhk="3 BHK", budget_max=21000000, description="Wants east facing, not ground floor")
    r = client.get(f"/api/v1/ai/leads/{lead['id']}/smart-matches").get_json()["data"]
    assert 1 <= len(r["picks"]) <= 3 and all(p["unit"]["floor"] != 0 for p in r["picks"][:1])
    assert "east facing" in r["preferences"] and "Priya" in r["message"]
    hold = r["picks"][0]["hold"]
    approve(client, hold)
    assert client.get(f"/api/v1/units/{r['picks'][0]['unit']['id']}").get_json()["data"]["status"] == "on_hold"
    rev = client.get(f"/api/v1/ai/units/{r['picks'][1]['unit']['id']}/lead-matches").get_json()["data"]
    assert rev["leads"][0]["id"] == lead["id"] and "{first_name}" in rev["message"]


def test_whatsapp_helper_reads_chat_and_proposes_fields(client):
    lead = _lead(client)
    chat = "[12/10/26, 10:01 AM] Priya Sharma: Hi, 2bhk chahiye Baner mein\n[12/10/26, 10:03 AM] Agent: Sure ji\n[12/10/26, 10:05 AM] Priya Sharma: budget 80 lakh tak hai"
    r = client.post("/api/v1/ai/whatsapp-assist", json={"conversation": chat, "lead_id": lead["id"]}).get_json()["data"]
    assert r["reply"] and r["language"] == "hinglish" and r["summary"]
    p = r["proposals"][0]
    assert {c["key"] for c in p["changes"]} >= {"bhk", "budget_max"}
    r2 = client.post("/api/v1/ai/whatsapp-assist", json={"conversation": "Ready to pay token amount today for 1204"}).get_json()["data"]
    assert r2["hot"] is True or r2["signals"]


def test_my_day_search_automation_import_and_insights(client):
    lead = _lead(client, intent="buy", bhk="3 BHK", budget_max=14000000, location="Sector 62", next_follow_up_at=dt.datetime.now(dt.timezone.utc).isoformat())
    _lead(client, first_name="Rohan", phone="9822222222", bhk="2 BHK", budget_max=6000000)
    day = client.get("/api/v1/ai/my-day").get_json()["data"]
    assert day["counts"]["follow_ups"] == 1 and day["sections"][1]["items"][0]["whatsapp"].startswith("https://wa.me/91")
    assert "follow-up" in client.post("/api/v1/ai/my-day/intro", json={}).get_json()["data"]["text"]
    team = client.get("/api/v1/ai/my-day", query_string={"team": "1"}).get_json()["data"]
    assert team["team"][0]["new_leads"] == 2

    s = client.post("/api/v1/ai/parse-search", json={"query": "3BHK buyers in Sector 62 under 1.5 Cr"}).get_json()["data"]
    assert s["params"]["bhk"] == "3 BHK" and s["params"]["budget_max_max"] == "15000000" and s["params"]["location"] == "Sector 62"
    rows = client.get("/api/v1/leads", query_string=s["params"]).get_json()["data"]
    assert [x["id"] for x in rows] == [lead["id"]]

    a = client.post("/api/v1/ai/automation-draft", json={"text": "When a new lead comes in, assign it round robin, create a call task, wait 2 days, then notify the owner"})
    a = a.get_json()["data"]
    assert [x["action_type"] for x in a["steps"]] == ["assign_user", "create_task", "delay", "send_notification"]
    assert client.post("/api/v1/automations", json={"name": a["name"], "trigger_type": a["trigger_type"], "graph": a["graph"], "is_active": False}).status_code == 201

    m = client.post("/api/v1/ai/import-assist", json={"entity": "leads", "headers": ["Naam", "Mobile No", "Config", "Budget"],
                                                     "rows": [{"Naam": "Kiran", "Mobile No": "98765-11111", "Config": "2bhk", "Budget": "85 lakh"}]}).get_json()["data"]
    assert m["mapping"]["phone"] == "Mobile No" and m["mapping"]["bhk"] == "Config" and m["mapping"]["budget"] == "Budget"
    mapping = {**m["mapping"], "first_name": "Naam"}
    rows = [{"Naam": "Kiran", "Mobile No": "98765-11111", "Config": "2bhk", "Budget": "80L - 1 Cr"}]
    assert client.post("/api/v1/import/commit", json={"entity_type": "leads", "mapping": mapping, "rows": rows}).get_json()["data"]["created"] == 1
    k = next(x for x in client.get("/api/v1/leads", query_string={"q": "Kiran"}).get_json()["data"])
    assert k["phone"] == "+91 98765 11111" and k["bhk"] == "2 BHK" and float(k["budget_min"]) == 8000000 and float(k["budget_max"]) == 10000000

    for url in ("/api/v1/ai/loss-analysis", "/api/v1/ai/inventory-advice", "/api/v1/ai/coaching"):
        assert client.get(url).status_code == 200, url
    pid, _ = _project(client)
    w = client.post("/api/v1/ai/listing", json={"kind": "whatsapp", "project_id": pid}).get_json()["data"]
    assert "Ireo Victory Valley" in w["text"]


def test_data_fixes_and_ai_automation_steps(client):
    lead = _lead(client, phone="09876500000", description="needs 2bhk around 70 lakh")
    fixes = client.get("/api/v1/ai/data-fixes").get_json()["data"]
    assert {f["title"].split()[0] for f in fixes} == {"Format", "Fill"}
    for f in fixes:
        approve(client, f)
    got = client.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]
    assert got["phone"] == "+91 98765 00000" and got["bhk"] == "2 BHK" and float(got["budget_max"]) == 7000000



def test_ai_steps_inside_automations_tag_and_fill(client):
    graph = {"nodes": [{"id": "t", "type": "trigger", "data": {"trigger_type": "lead.created"}},
                       {"id": "a", "type": "action", "data": {"action_type": "ai_extract_requirements", "config": {}}},
                       {"id": "b", "type": "action", "data": {"action_type": "ai_classify_lead", "config": {}}}],
             "edges": [{"id": "e1", "source": "t", "target": "a"}, {"id": "e2", "source": "a", "target": "b"}]}
    assert client.post("/api/v1/automations", json={"name": "Triage", "trigger_type": "lead.created", "graph": graph, "is_active": True}).status_code == 201
    lead = _lead(client, description="I am a channel partner, we have resale inventory of 3bhk under 2 cr")
    got = client.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]
    assert "broker" in got["tags"] and got["bhk"] == "3 BHK"


def test_calls_follow_meetings_permission(app):
    from app.models import Role, WorkspaceMember

    cl, me = signup(app)
    lead = _lead(cl)
    with app.app_context(), bypass_scope():
        sales = db.session.query(Role).filter_by(key="sales").first() or db.session.query(Role).filter(Role.key != "owner", Role.rank >= 40).first()
        m = db.session.query(WorkspaceMember).filter_by(user_id=me["user"]["id"]).one()
        m.role_id = sales.id
        db.session.commit()
    assert cl.post("/api/v1/calls", json={"lead_id": lead["id"], "outcome": "connected"}).status_code == 201


def test_key_test_shows_the_providers_reason(client, monkeypatch):
    reasons = {
        "sk-ant-broke-0001": (400, {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low to access the Anthropic API."}}, "ai_quota"),
        "sk-ant-model-0002": (400, {"type": "error", "error": {"type": "invalid_request_error", "message": "model: claude-x not found"}}, "ai_model_missing"),
        "sk-ant-other-0003": (400, {"type": "error", "error": {"type": "invalid_request_error", "message": "max_tokens: must be greater than thinking budget"}}, "ai_request_rejected"),
    }

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        status, body, _ = reasons[headers["x-api-key"]]
        return FakeResponse(status, body)

    monkeypatch.setattr(httpx, "post", fake_post)
    for key, (_, body, code) in reasons.items():
        r = client.put("/api/v1/ai/settings", json={"provider": "anthropic", "api_key": key})
        err = r.get_json()["error"]
        assert r.status_code == 400 and err["code"] == code, err
        assert ("claude-haiku-5-5" if code == "ai_model_missing" else body["error"]["message"]) in err["message"]


def test_reopened_chat_remembers_what_was_approved(client):
    lead = _lead(client)
    r = client.post("/api/v1/ai/chat", json={"message": "Remind me to call this lead tomorrow", "page": {"entity": "lead", "id": lead["id"]}}).get_json()["data"]
    p = r["proposals"][0]
    approve(client, p)
    assert client.post("/api/v1/ai/proposals/outcome", json={"kind": p["kind"], "title": p["title"], "outcome": "approved", "proposal_id": p["id"],
                                                              "result_url": "/app/tasks"}).status_code == 204
    saved = client.get(f"/api/v1/ai/conversations/{r['conversation_id']}").get_json()["data"]["messages"][-1]["proposals"][0]
    assert saved["status"] == "approved" and saved["result_url"] == "/app/tasks"
    # a later failure report doesn't undo the saved state
    client.post("/api/v1/ai/proposals/outcome", json={"kind": p["kind"], "title": p["title"], "outcome": "failed", "proposal_id": p["id"]})
    assert client.get(f"/api/v1/ai/conversations/{r['conversation_id']}").get_json()["data"]["messages"][-1]["proposals"][0]["status"] == "approved"


def test_openrouter_retired_default_falls_back(client, monkeypatch):
    sent = []

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        sent.append(json["model"])
        if json["model"] == "anthropic/claude-haiku-5.5":
            return FakeResponse(400, {"error": {"code": 400, "message": "anthropic/claude-haiku-5.5 is not a valid model ID"}})
        return FakeResponse(200, {"choices": [{"message": {"content": "OK"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 1}, "model": json["model"]})

    monkeypatch.setattr(httpx, "post", fake_post)
    r = client.put("/api/v1/ai/settings", json={"provider": "openrouter", "api_key": "sk-or-v1-test-0001"})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert sent == ["anthropic/claude-haiku-5.5", "openrouter/auto"]
    assert d["connected"] and d["fast_model"] == "openrouter/auto" and d["smart_model"] == "openrouter/auto"

    # a model the admin typed is never swapped out behind their back
    sent.clear()
    r = client.put("/api/v1/ai/settings", json={"provider": "openrouter", "api_key": "sk-or-v1-test-0002", "fast_model": "anthropic/claude-haiku-5.5"})
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "ai_model_missing"
    assert sent == ["anthropic/claude-haiku-5.5"]
