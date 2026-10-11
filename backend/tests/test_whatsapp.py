import hashlib
import hmac
import io
import json
import time

import httpx

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import Integration, WhatsAppMessage
from app.services import whatsapp
from tests.test_realestate import _project


def _unit(cl):
    pid, tid = _project(cl)
    uid = cl.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]["floors"][0]["units"][0]["id"]
    return pid, uid


def _upload(cl, name="brochure.pdf", **form):
    r = cl.c.post("/api/v1/files", data={"file": (io.BytesIO(b"%PDF-1.4 test"), name, "application/pdf"), **form}, headers=cl._h(), content_type="multipart/form-data")
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def _token(app):
    with app.app_context(), bypass_scope():
        return db.session.query(Integration).filter_by(provider="whatsapp").one().config["webhook_token"]


def _inbound(wamid, phone, text, name="Rohit Sharma"):
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": "PNID"}, "contacts": [{"wa_id": phone, "profile": {"name": name}}],
        "messages": [{"from": phone, "id": wamid, "timestamp": str(int(time.time())), "type": "text", "text": {"body": text}}]}}]}]}


def test_normalize_phone(app):
    with app.app_context():
        assert whatsapp.normalize_phone("+91 98765-43210") == "919876543210"
        assert whatsapp.normalize_phone("098765 43210") == "919876543210"
        assert whatsapp.normalize_phone("9876543210") == "919876543210"
        assert whatsapp.normalize_phone("+1 (415) 555-0100") == "14155550100"
        assert whatsapp.normalize_phone("12") is None


def test_sandbox_templates_brochure_and_replies_on_timeline(client):
    r = client.post("/api/v1/integrations/whatsapp/connect", json={})
    assert r.status_code == 200 and r.get_json()["data"]["mode"] == "sandbox"
    assert "/api/v1/inbound/whatsapp/" in r.get_json()["data"]["webhook"]["url"]
    lead = client.post("/api/v1/leads", json={"first_name": "Rohit", "last_name": "Sharma", "phone": "+91 98765 43210"}).get_json()["data"]

    # template to a lead
    tpls = client.get("/api/v1/whatsapp/templates").get_json()["data"]
    t = next(t for t in tpls if t["name"] == "site_visit_reminder")
    assert client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "template": {"name": t["name"], "language": t["language"], "params": ["Rohit"]}}).status_code == 422
    r = client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "template": {"name": t["name"], "language": t["language"], "params": ["Rohit", "Victory Valley", "Sat 11am"]}})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["data"]["body"].startswith("Hi Rohit, a reminder about your site visit to Victory Valley")

    # a brochure outside the 24h window needs a media template
    pid, uid = _unit(client)
    _upload(client, "Victory Valley brochure.pdf", project_id=pid, doc_kind="brochure")
    fp = _upload(client, "301 floor plan.pdf", unit_id=uid, doc_kind="floor_plan")
    assert fp["project_id"] == pid
    docs = client.get(f"/api/v1/units/{uid}/documents").get_json()["data"]
    assert [(d["doc_kind"], d["scope"]) for d in docs] == [("floor_plan", "unit"), ("brochure", "project")]
    r = client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "file_id": fp["id"], "unit_id": uid})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "whatsapp_window_closed"
    assert client.patch("/api/v1/whatsapp/settings", json={"media_template": "hello_world|en_US"}).status_code == 422
    assert client.patch("/api/v1/whatsapp/settings", json={"media_template": "property_brochure|en"}).status_code == 200
    r = client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "file_id": fp["id"], "unit_id": uid})
    assert r.status_code == 201, r.get_json()
    m = r.get_json()["data"]
    assert m["kind"] == "template" and m["template_name"] == "property_brochure" and m["unit_id"] == uid and "Unit 301" in m["body"]
    assert client.get(f"/api/v1/units/{uid}/history").get_json()["data"][0]["note"] == "Floor plan sent to Rohit Sharma on WhatsApp"

    # client replies: logged on the lead's timeline, opens the 24h window, and Meta retries are ignored
    tok = _token(client.app)
    for _ in range(2):
        r = client.post(f"/api/v1/inbound/whatsapp/{tok}", json=_inbound("wamid.IN1", "919876543210", "Is the 3 BHK east facing?"))
        assert r.status_code == 200
    tl = client.get(f"/api/v1/timeline?entity=lead&id={lead['id']}").get_json()["data"]
    replies = [a for a in tl if a["type"] == "whatsapp" and a["title"].startswith("WhatsApp reply")]
    assert len(replies) == 1 and replies[0]["body"] == "Is the 3 BHK east facing?"
    conv = client.get(f"/api/v1/whatsapp/conversation?lead_id={lead['id']}").get_json()["data"]
    assert conv["window_open"] is True and [x["direction"] for x in conv["messages"]] == ["outbound", "outbound", "inbound"]

    # inside the window documents and free text go out directly
    r = client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "file_id": fp["id"], "unit_id": uid, "caption": "Here you go"})
    assert r.status_code == 201 and r.get_json()["data"]["kind"] == "document"
    assert client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "text": "Yes, east facing."}).status_code == 201

    # delivery receipts move status forward only
    wamid = m["wa_message_id"]
    for st in ("read", "delivered"):
        client.post(f"/api/v1/inbound/whatsapp/{tok}", json={"entry": [{"changes": [{"field": "messages", "value": {"statuses": [{"id": wamid, "status": st}]}}]}]})
    with client.app.app_context(), bypass_scope():
        assert db.session.query(WhatsAppMessage).filter_by(wa_message_id=wamid).one().status == "read"


def test_unknown_number_becomes_a_lead(client):
    client.post("/api/v1/integrations/whatsapp/connect", json={})
    tok = _token(client.app)
    assert client.post(f"/api/v1/inbound/whatsapp/{tok}", json=_inbound("wamid.NEW", "919000000001", "Price of 2 BHK?", name="Neha Kapoor")).get_json()["data"]["messages"] == 1
    leads = client.get("/api/v1/leads").get_json()["data"]
    assert leads[0]["first_name"] == "Neha" and leads[0]["source"] == "whatsapp" and leads[0]["phone"] == "+919000000001"


def test_live_connect_verifies_with_meta_and_webhook_checks_signature(client, monkeypatch):
    def fake_get(url, **kw):
        assert kw["headers"]["Authorization"] == "Bearer TOKEN"
        return httpx.Response(200, json={"display_phone_number": "+91 99999 00000", "verified_name": "Acme Realty"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(whatsapp.httpx, "get", fake_get)
    assert client.post("/api/v1/integrations/whatsapp/connect", json={"phone_number_id": "PNID"}).status_code == 422  # partial details
    r = client.post("/api/v1/integrations/whatsapp/connect", json={"phone_number_id": "PNID", "waba_id": "WABA", "access_token": "TOKEN", "app_secret": "s3cret"})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert d["mode"] == "live" and d["account_label"] == "Acme Realty · +91 99999 00000"
    assert "access_token" not in json.dumps(client.get("/api/v1/integrations").get_json())

    tok = _token(client.app)
    vt = d["webhook"]["verify_token"]
    assert client.get(f"/api/v1/inbound/whatsapp/{tok}?hub.mode=subscribe&hub.verify_token={vt}&hub.challenge=42").data == b"42"
    assert client.get(f"/api/v1/inbound/whatsapp/{tok}?hub.mode=subscribe&hub.verify_token=nope&hub.challenge=42").status_code == 403

    body = json.dumps(_inbound("wamid.SIG", "919876543210", "hi")).encode()
    assert client.c.post(f"/api/v1/inbound/whatsapp/{tok}", data=body, content_type="application/json").status_code == 401
    sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert client.c.post(f"/api/v1/inbound/whatsapp/{tok}", data=body, content_type="application/json", headers={"X-Hub-Signature-256": sig}).status_code == 200

    sent = {}

    def fake_post(url, **kw):
        sent.update(url=url, json=kw["json"])
        return httpx.Response(200, json={"messages": [{"id": "wamid.OUT"}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(whatsapp.httpx, "post", fake_post)
    monkeypatch.setattr(whatsapp, "list_templates", lambda i: whatsapp.SANDBOX_TEMPLATES)
    lead = client.get("/api/v1/leads").get_json()["data"][0]
    r = client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "template": {"name": "hello_world", "language": "en_US"}})
    assert r.status_code == 201, r.get_json()
    assert sent["url"].endswith("/PNID/messages") and sent["json"]["to"] == "919876543210" and sent["json"]["template"]["name"] == "hello_world"


def test_feature_gate_and_bad_token(client):
    assert client.post("/api/v1/inbound/whatsapp/not-a-real-token-at-all", json={}).status_code == 404
    assert client.get("/api/v1/whatsapp/templates").get_json()["error"]["code"] == "whatsapp_not_connected"
