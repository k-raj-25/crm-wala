import hashlib
import hmac
import io
import json
import time

import httpx
import pytest

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import Integration, WhatsAppMessage
from app.services import whatsapp
from tests.test_realestate import _project

CREDS = {"phone_number_id": "PNID", "waba_id": "WABA", "access_token": "TOKEN", "app_secret": "s3cret"}
TEMPLATES = [
    {"name": "hello_world", "language": "en_US", "status": "APPROVED", "category": "UTILITY", "components": [{"type": "BODY", "text": "Hello World!"}]},
    {"name": "site_visit_reminder", "language": "en", "status": "APPROVED", "category": "UTILITY",
     "components": [{"type": "BODY", "text": "Hi {{1}}, a reminder about your site visit to {{2}} on {{3}}."}]},
    {"name": "visit_named", "language": "en", "status": "APPROVED", "category": "UTILITY",
     "components": [{"type": "BODY", "text": "Hi {{first_name}}, see you at {{project}}."}]},
    {"name": "property_brochure", "language": "en", "status": "APPROVED", "category": "MARKETING",
     "components": [{"type": "HEADER", "format": "DOCUMENT"}, {"type": "BODY", "text": "Hi {{1}}, here are the details for {{2}} you asked about."}]},
    {"name": "book_now", "language": "en", "status": "APPROVED", "category": "MARKETING",
     "components": [{"type": "BODY", "text": "Book now"}, {"type": "BUTTONS", "buttons": [{"type": "URL", "url": "https://x.io/{{1}}"}]}]},
]


class FakeMeta:
    """Stands in for graph.facebook.com: records what we send and answers like the Cloud API."""

    def __init__(self):
        self.messages, self.uploads, self.subscribed, self.n = [], [], False, 0
        self.fail_next: dict | None = None

    def get(self, url, params=None, headers=None, **kw):
        assert headers["Authorization"] == "Bearer TOKEN"
        if url.endswith("/PNID"):
            return self._r(200, {"display_phone_number": "+91 99999 00000", "verified_name": "Acme Realty"})
        if url.endswith("/WABA/message_templates"):
            return self._r(200, {"data": TEMPLATES})
        return self._r(400, {"error": {"message": "Unsupported get request", "code": 100}})

    def post(self, url, json=None, data=None, files=None, headers=None, **kw):
        if url.endswith("/WABA/subscribed_apps"):
            self.subscribed = True
            return self._r(200, {"success": True})
        if url.endswith("/PNID/media"):
            self.uploads.append({"data": data, "filename": files["file"][0], "bytes": files["file"][1]})
            return self._r(200, {"id": f"MEDIA{len(self.uploads)}"})
        if url.endswith("/PNID/messages"):
            if self.fail_next:
                err, self.fail_next = self.fail_next, None
                return self._r(400, {"error": err})
            self.messages.append(json)
            self.n += 1
            return self._r(200, {"messages": [{"id": f"wamid.OUT{self.n}"}]})
        return self._r(404, {"error": {"message": "unknown"}})

    @staticmethod
    def _r(status, body):
        return httpx.Response(status, json=body, request=httpx.Request("GET", "https://graph.facebook.com"))


@pytest.fixture()
def meta(monkeypatch):
    m = FakeMeta()
    monkeypatch.setattr(whatsapp.httpx, "get", m.get)
    monkeypatch.setattr(whatsapp.httpx, "post", m.post)
    return m


def _connect(cl):
    r = cl.post("/api/v1/integrations/whatsapp/connect", json=CREDS)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


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


def _hook(cl, payload, secret=b"s3cret"):
    """POST to our webhook exactly as Meta does: raw JSON body signed with the app secret."""
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return cl.c.post(f"/api/v1/inbound/whatsapp/{_token(cl.app)}", data=body, content_type="application/json", headers={"X-Hub-Signature-256": sig})


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


def test_connect_requires_real_details_verifies_and_subscribes(client, meta):
    r = client.post("/api/v1/integrations/whatsapp/connect", json={})
    assert r.status_code == 422 and set(r.get_json()["error"]["details"]) == set(CREDS)  # no sandbox: everything is required
    d = _connect(client)
    assert meta.subscribed and d["mode"] == "live" and d["account_label"] == "Acme Realty · +91 99999 00000"
    assert "/api/v1/inbound/whatsapp/" in d["webhook"]["url"] and d["webhook"]["verify_token"]
    assert "TOKEN" not in json.dumps(client.get("/api/v1/integrations").get_json())
    # reconnecting with only a new token keeps the other stored details and the webhook
    tok = _token(client.app)
    r = client.post("/api/v1/integrations/whatsapp/connect", json={"access_token": "TOKEN"})
    assert r.status_code == 200 and _token(client.app) == tok


def test_templates_brochures_and_replies_on_timeline(client, meta):
    _connect(client)
    lead = client.post("/api/v1/leads", json={"first_name": "Rohit", "last_name": "Sharma", "phone": "+91 98765 43210"}).get_json()["data"]
    tpls = {t["name"]: t for t in client.get("/api/v1/whatsapp/templates").get_json()["data"]}
    assert tpls["book_now"]["supported"] is False and tpls["visit_named"]["param_names"] == ["first_name", "project"]

    # positional and named templates
    t = tpls["site_visit_reminder"]
    assert client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "template": {"name": t["name"], "language": "en", "params": ["Rohit"]}}).status_code == 422
    r = client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "template": {"name": t["name"], "language": "en", "params": ["Rohit", "Victory Valley", "Sat 11am"]}})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["data"]["body"] == "Hi Rohit, a reminder about your site visit to Victory Valley on Sat 11am."
    assert meta.messages[-1]["to"] == "919876543210" and meta.messages[-1]["template"]["components"][0]["parameters"][0] == {"type": "text", "text": "Rohit"}
    r = client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "template": {"name": "visit_named", "language": "en", "params": ["Rohit", "Victory Valley"]}})
    assert r.status_code == 201 and r.get_json()["data"]["body"] == "Hi Rohit, see you at Victory Valley."
    assert meta.messages[-1]["template"]["components"][0]["parameters"][1] == {"type": "text", "parameter_name": "project", "text": "Victory Valley"}
    assert client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "template": {"name": "book_now", "language": "en"}}).status_code == 422

    # documents on the unit and its project; outside the 24h window a file needs the brochure template
    pid, uid = _unit(client)
    _upload(client, "Victory Valley brochure.pdf", project_id=pid, doc_kind="brochure")
    fp = _upload(client, "301 floor plan.pdf", unit_id=uid, doc_kind="floor_plan")
    docs = client.get(f"/api/v1/units/{uid}/documents").get_json()["data"]
    assert [(d["doc_kind"], d["scope"]) for d in docs] == [("floor_plan", "unit"), ("brochure", "project")]
    r = client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "file_id": fp["id"], "unit_id": uid})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "whatsapp_window_closed"
    assert client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "text": "hi"}).get_json()["error"]["code"] == "whatsapp_window_closed"
    assert client.patch("/api/v1/whatsapp/settings", json={"media_template": "hello_world|en_US"}).status_code == 422
    assert client.patch("/api/v1/whatsapp/settings", json={"media_template": "property_brochure|en"}).status_code == 200
    r = client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "file_id": fp["id"], "unit_id": uid})
    assert r.status_code == 201, r.get_json()
    m = r.get_json()["data"]
    assert m["kind"] == "template" and m["template_name"] == "property_brochure" and "Unit 301" in m["body"]
    # the file is uploaded to Meta's media store and referenced by id, never by a public link
    assert meta.uploads[-1]["bytes"] == b"%PDF-1.4 test" and meta.uploads[-1]["data"]["type"] == "application/pdf"
    assert meta.messages[-1]["template"]["components"][0] == {"type": "header", "parameters": [{"type": "document", "document": {"id": "MEDIA1", "filename": "301 floor plan.pdf"}}]}
    assert client.get(f"/api/v1/units/{uid}/history").get_json()["data"][0]["note"] == "Floor plan sent to Rohit Sharma on WhatsApp"

    # the client replies: on the lead's timeline once (Meta retries are ignored), and the 24h window opens
    for _ in range(2):
        assert _hook(client, _inbound("wamid.IN1", "919876543210", "Is the 3 BHK east facing?")).status_code == 200
    tl = client.get(f"/api/v1/timeline?entity=lead&id={lead['id']}").get_json()["data"]
    replies = [a for a in tl if a["type"] == "whatsapp" and a["title"].startswith("WhatsApp reply")]
    assert len(replies) == 1 and replies[0]["body"] == "Is the 3 BHK east facing?"
    conv = client.get(f"/api/v1/whatsapp/conversation?lead_id={lead['id']}").get_json()["data"]
    assert conv["window_open"] is True and conv["messages"][-1]["direction"] == "inbound"

    # inside the window documents and free text go out directly
    r = client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "file_id": fp["id"], "unit_id": uid, "caption": "Here you go"})
    assert r.status_code == 201 and r.get_json()["data"]["kind"] == "document"
    assert meta.messages[-1]["document"] == {"id": "MEDIA2", "filename": "301 floor plan.pdf", "caption": "Here you go"}
    assert client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "text": "Yes, east facing."}).status_code == 201

    # delivery receipts move status forward only
    for st in ("read", "delivered"):
        _hook(client, {"entry": [{"changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": "PNID"}, "statuses": [{"id": m["wa_message_id"], "status": st}]}}]}]})
    with client.app.app_context(), bypass_scope():
        assert db.session.query(WhatsAppMessage).filter_by(wa_message_id=m["wa_message_id"]).one().status == "read"


def test_webhook_security(client, meta):
    d = _connect(client)
    tok, vt = _token(client.app), d["webhook"]["verify_token"]
    assert client.get(f"/api/v1/inbound/whatsapp/{tok}?hub.mode=subscribe&hub.verify_token={vt}&hub.challenge=42").data == b"42"
    assert client.get(f"/api/v1/inbound/whatsapp/{tok}?hub.mode=subscribe&hub.verify_token=nope&hub.challenge=42").status_code == 403
    payload = _inbound("wamid.SIG", "919876543210", "hi")
    assert client.c.post(f"/api/v1/inbound/whatsapp/{tok}", json=payload).status_code == 401  # unsigned
    assert _hook(client, payload, secret=b"wrong").status_code == 401
    assert _hook(client, payload).status_code == 200
    assert client.post("/api/v1/inbound/whatsapp/not-a-real-token-at-all", json={}).status_code == 404


def test_unknown_number_becomes_a_lead(client, meta):
    _connect(client)
    assert _hook(client, _inbound("wamid.NEW", "919000000001", "Price of 2 BHK?", name="Neha Kapoor")).get_json()["data"]["messages"] == 1
    leads = client.get("/api/v1/leads").get_json()["data"]
    assert leads[0]["first_name"] == "Neha" and leads[0]["source"] == "whatsapp" and leads[0]["phone"] == "+919000000001"


def test_expired_token_asks_to_reconnect(client, meta):
    _connect(client)
    lead = client.post("/api/v1/leads", json={"first_name": "Asha", "phone": "9876500000"}).get_json()["data"]
    meta.fail_next = {"message": "Error validating access token", "code": 190}
    r = client.post("/api/v1/whatsapp/send", json={"lead_id": lead["id"], "template": {"name": "hello_world", "language": "en_US"}})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "whatsapp_reconnect"
    wa = next(i for i in client.get("/api/v1/integrations").get_json()["data"]["integrations"] if i["provider"] == "whatsapp")
    assert wa["status"] == "reconnect"


def test_not_connected(client):
    assert client.get("/api/v1/whatsapp/templates").get_json()["error"]["code"] == "whatsapp_not_connected"
