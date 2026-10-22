import httpx
import pytest

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import Call, Integration, Lead
from app.services.telephony import exotel
from tests.conftest import signup
from tests.test_phone_privacy import _member

CREDS = {"account_sid": "acme1", "api_key": "KEY", "api_token": "TOKEN", "subdomain": "api.in.exotel.com", "exophone": "080 4719 0000"}
CLIENT = "+91 98765 43210"
OWNER_PHONE, REP_PHONE, MGR_PHONE = "+91 90000 00001", "+91 90000 00002", "+91 90000 00003"


class FakeExotel:
    def __init__(self):
        self.calls, self.n, self.refuse = [], 0, None

    def request(self, method, url, auth=None, data=None, **kw):
        req = httpx.Request(method, url)
        if auth != ("KEY", "TOKEN"):
            return httpx.Response(401, json={"RestException": {"Message": "Authentication failed"}}, request=req)
        if url == "https://api.in.exotel.com/v1/Accounts/acme1/Balance.json":
            return httpx.Response(200, json={"Account": {"AccountSid": "acme1", "BalanceData": {"Balance": "500"}}}, request=req)
        if url == "https://api.in.exotel.com/v1/Accounts/acme1/Calls/connect.json":
            if self.refuse:
                return httpx.Response(403, json={"RestException": {"Status": 403, "Message": self.refuse}}, request=req)
            self.n += 1
            self.calls.append(data)
            return httpx.Response(200, json={"Call": {"Sid": f"OUT{self.n}", "Status": "in-progress"}}, request=req)
        return httpx.Response(404, json={"RestException": {"Message": "Not found"}}, request=req)


@pytest.fixture()
def exo(monkeypatch):
    f = FakeExotel()
    monkeypatch.setattr(exotel.httpx, "request", f.request)
    return f


def _profile(cl, phone):
    r = cl.patch("/api/v1/me/preferences", json={"phone": phone})
    assert r.status_code == 200, r.get_json()


def _connect(cl, **over):
    r = cl.post("/api/v1/integrations/exotel/connect", json={**CREDS, **over})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def _hook(cl, data, name):
    return next(h["url"] for h in data["calling"]["hooks"] if h["key"] == name).split("/api/v1/")[1]


def _user_id(cl):
    return cl.get("/api/v1/auth/me").get_json()["data"]["user"]["id"]


def _team(app):
    owner, _ = signup(app)
    _profile(owner, OWNER_PHONE)
    rep = _member(app, owner, "sales_rep", "rep@acme.io")
    _profile(rep, REP_PHONE)
    mgr = _member(app, owner, "manager", "mgr@acme.io")
    _profile(mgr, MGR_PHONE)
    return owner, rep, mgr


def test_connect_checks_credentials_and_gives_webhooks(app, exo):
    owner, _ = signup(app)
    r = owner.post("/api/v1/integrations/exotel/connect", json={**CREDS, "api_token": "wrong"})
    assert r.status_code == 422
    data = _connect(owner)
    assert data["account_label"] == "Exotel · +918047190000"
    assert {h["key"] for h in data["calling"]["hooks"]} == {"connect", "handover"}
    assert all(f.get("value") is None for f in data["calling"]["fields"] if f.get("secret"))
    st = owner.get("/api/v1/calling/status").get_json()["data"]
    assert st["enabled"] and st["my_phone_set"] is False


def test_rep_calls_a_hidden_number_through_the_company_number(app, exo):
    owner, rep, _ = _team(app)
    _connect(owner)
    lead = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "phone": CLIENT}).get_json()["data"]
    r = rep.post("/api/v1/calling/call", json={"lead_id": lead["id"]})
    assert r.status_code == 201, r.get_json()
    live = r.get_json()["data"]
    assert live["status"] == "ringing" and "•" in live["phone"] and live["record"]["name"] == "Jasmine"
    sent = exo.calls[0]
    assert sent["From"] == "+919000000002" and sent["To"] == "+919876543210" and sent["CallerId"] == "080 4719 0000"
    # the rep's live-call bar
    rows = rep.get("/api/v1/calling/active").get_json()["data"]
    assert [c["id"] for c in rows] == [live["id"]] and rows[0]["can_transfer"] is False
    # Exotel reports the end of the call; the call is logged on the lead
    with app.app_context(), bypass_scope():
        i = db.session.query(Integration).filter_by(provider="exotel").one()
        token = i.config["webhook_token"]
    r = rep.c.post(f"/api/v1/inbound/calls/{token}/status", json={"CallSid": "OUT1", "EventType": "terminal", "Status": "completed", "ConversationDuration": 75,
                                                                  "RecordingUrl": "https://recordings.exotel.com/x.mp3"})
    assert r.status_code == 200
    with app.app_context(), bypass_scope():
        c = db.session.query(Call).filter_by(provider_call_id="OUT1").one()
        assert c.status == "completed" and c.duration_seconds == 75 and c.outcome == "connected"
        assert db.session.get(Lead, c.lead_id).last_contacted_at is not None
    assert rep.get("/api/v1/calling/active").get_json()["data"] == []
    calls = rep.get(f"/api/v1/calls?lead_id={lead['id']}").get_json()["data"]
    assert "•" in calls[0]["phone"]


def test_calling_needs_your_own_phone_and_permission(app, exo):
    owner, _ = signup(app)
    _connect(owner)
    lead = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "phone": CLIENT}).get_json()["data"]
    r = owner.post("/api/v1/calling/call", json={"lead_id": lead["id"]})
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "calling_no_phone"
    viewer = _member(app, owner, "viewer", "viewer@acme.io")
    assert viewer.post("/api/v1/calling/call", json={"lead_id": lead["id"]}).status_code == 403


def test_callback_rings_the_lead_owner_then_the_owner(app, exo):
    owner, rep, _ = _team(app)
    data = _connect(owner)
    lead = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "phone": CLIENT, "owner_id": _user_id(rep)}).get_json()["data"]
    r = owner.c.get(f"/api/v1/{_hook(owner, data, 'connect')}", query_string={"CallSid": "IN1", "CallFrom": "09876543210", "CallTo": "08047190000"})
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["destination"]["numbers"] == ["+919000000002", "+919000000001"]
    assert "Rep" in body["start_call_playback"]["value"]
    with app.app_context(), bypass_scope():
        c = db.session.query(Call).filter_by(provider_call_id="IN1").one()
        assert c.direction == "inbound" and str(c.lead_id) == lead["id"] and str(c.user_id) == _user_id(rep)
    assert rep.get("/api/v1/calling/active").get_json()["data"][0]["record"]["name"] == "Jasmine"

    # setting: always ring the fallback person, and only them
    owner.patch("/api/v1/calling/settings", json={"inbound": "fallback", "ring_fallback_too": False})
    r = owner.c.get(f"/api/v1/{_hook(owner, data, 'connect')}", query_string={"CallSid": "IN2", "CallFrom": "09876543210"})
    assert r.get_json()["destination"]["numbers"] == ["+919000000001"]


def test_unknown_caller_becomes_a_lead_for_the_owner(app, exo):
    owner, _ = signup(app)
    _profile(owner, OWNER_PHONE)
    data = _connect(owner)
    r = owner.c.get(f"/api/v1/{_hook(owner, data, 'connect')}", query_string={"CallSid": "IN9", "CallFrom": "+919811122233"})
    assert r.get_json()["destination"]["numbers"] == ["+919000000001"]
    leads = owner.get("/api/v1/leads").get_json()["data"]
    assert leads[0]["source"] == "call" and leads[0]["phone"] == "+919811122233" and "9811" not in leads[0]["first_name"] + (leads[0]["last_name"] or "")
    # the client hangs up before anyone answers: a missed call
    owner.c.get(f"/api/v1/{_hook(owner, data, 'handover')}", query_string={"CallSid": "IN9", "DialCallStatus": "no-answer"})
    with app.app_context(), bypass_scope():
        assert db.session.query(Call).filter_by(provider_call_id="IN9").one().status == "missed"


def test_rep_hands_a_callback_to_their_manager_only(app, exo):
    owner, rep, mgr = _team(app)
    data = _connect(owner)
    lead = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "phone": CLIENT, "owner_id": _user_id(rep)}).get_json()["data"]
    # rep reports to the manager
    members = owner.get("/api/v1/team/members").get_json()["data"]
    rep_m = next(m for m in members if m["email"] == "rep@acme.io")
    assert owner.patch(f"/api/v1/calling/members/{rep_m['id']}/manager", json={"reports_to": _user_id(mgr)}).status_code == 200
    owner.c.get(f"/api/v1/{_hook(owner, data, 'connect')}", query_string={"CallSid": "IN1", "CallFrom": "09876543210"})
    owner.c.post(f"/api/v1/{_hook(owner, data, 'connect').replace('/connect', '/status')}", json={"CallSid": "IN1", "EventType": "answered", "DialWhomNumber": "09000000002"})
    call = rep.get("/api/v1/calling/active").get_json()["data"][0]
    assert call["status"] == "in_progress" and call["can_transfer"]
    t = rep.get(f"/api/v1/calling/calls/{call['id']}/transfer-targets").get_json()["data"]
    assert t["any"] is False and [x["name"] for x in t["targets"]] == ["Mgr", "Asha Rao"]
    # the rep can't hand it to just anyone
    viewer = _member(app, owner, "viewer", "viewer@acme.io")
    r = rep.post(f"/api/v1/calling/calls/{call['id']}/transfer", json={"to_user_id": _user_id(viewer)})
    assert r.status_code == 403
    r = rep.post(f"/api/v1/calling/calls/{call['id']}/transfer", json={"to_user_id": _user_id(mgr)})
    assert r.status_code == 200 and r.get_json()["data"]["pending_transfer"]["name"] == "Mgr"
    # the rep hangs up: the dial-end event is ignored, the flow's hand-over step moves the call to the manager
    owner.c.post(f"/api/v1/{_hook(owner, data, 'connect').replace('/connect', '/status')}",
                 json={"CallSid": "IN1", "DialCallStatus": "completed", "DialWhomNumber": "09000000002", "DialCallDuration": "40"})
    r = owner.c.get(f"/api/v1/{_hook(owner, data, 'handover')}", query_string={"CallSid": "IN1", "DialCallStatus": "completed", "DialCallDuration": "40",
                                                                              "DialWhomNumber": "09000000002"})
    assert r.status_code == 200
    r = owner.c.get(f"/api/v1/{_hook(owner, data, 'connect')}", query_string={"CallSid": "IN1", "CallFrom": "09876543210"})
    assert r.get_json()["destination"]["numbers"] == ["+919000000003", "+919000000002"]  # back to the rep if the manager doesn't pick up
    assert rep.get("/api/v1/calling/active").get_json()["data"] == []
    mine = mgr.get("/api/v1/calling/active").get_json()["data"]
    assert mine[0]["transferred_from"] == "Rep" and mine[0]["record"]["id"] == lead["id"]
    # the manager finishes the call
    owner.c.get(f"/api/v1/{_hook(owner, data, 'handover')}", query_string={"CallSid": "IN1", "DialCallStatus": "completed", "DialCallDuration": "90",
                                                                          "DialWhomNumber": "09000000003"})
    with app.app_context(), bypass_scope():
        c = db.session.query(Call).filter_by(provider_call_id="IN1").one()
        assert c.status == "completed" and c.duration_seconds == 130 and len(c.data["transfers"]) == 1


def test_owner_can_hand_a_call_to_anyone(app, exo):
    owner, rep, _ = _team(app)
    data = _connect(owner)
    owner.post("/api/v1/leads", json={"first_name": "Jasmine", "phone": CLIENT})
    owner.c.get(f"/api/v1/{_hook(owner, data, 'connect')}", query_string={"CallSid": "IN1", "CallFrom": "09876543210"})
    call = owner.get("/api/v1/calling/active").get_json()["data"][0]
    t = owner.get(f"/api/v1/calling/calls/{call['id']}/transfer-targets").get_json()["data"]
    assert t["any"] is True and {x["name"] for x in t["targets"]} == {"Rep", "Mgr"}
    assert owner.post(f"/api/v1/calling/calls/{call['id']}/transfer", json={"to_user_id": _user_id(rep)}).status_code == 200
    # someone else can't hand over a call they're not on
    assert rep.post(f"/api/v1/calling/calls/{call['id']}/transfer", json={"to_user_id": _user_id(owner)}).status_code == 403
    r = owner.c.get(f"/api/v1/{_hook(owner, data, 'handover')}", query_string={"CallSid": "IN1", "DialCallStatus": "completed"})
    assert r.status_code == 200
    assert rep.get("/api/v1/calling/active").get_json()["data"][0]["transferred_from"] == "Asha Rao"


def test_no_handover_waiting_ends_the_flow(app, exo):
    owner, _ = signup(app)
    _profile(owner, OWNER_PHONE)
    data = _connect(owner)
    owner.c.get(f"/api/v1/{_hook(owner, data, 'connect')}", query_string={"CallSid": "IN1", "CallFrom": "09876543210"})
    r = owner.c.get(f"/api/v1/{_hook(owner, data, 'handover')}", query_string={"CallSid": "IN1", "DialCallStatus": "completed", "DialCallDuration": "30"})
    assert r.status_code == 302
    assert owner.c.get("/api/v1/inbound/calls/not-a-real-token-123456/connect", query_string={"CallSid": "X"}).status_code == 404


def test_outgoing_client_first_runs_through_the_flow_and_can_be_handed_over(app, exo):
    owner, rep, mgr = _team(app)
    data = _connect(owner, flow_app_id="777")
    assert owner.patch("/api/v1/calling/settings", json={"client_first": True}).status_code == 200
    lead = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "phone": CLIENT}).get_json()["data"]
    live = rep.post("/api/v1/calling/call", json={"lead_id": lead["id"]}).get_json()["data"]
    sent = exo.calls[0]
    assert sent["From"] == "+919876543210" and sent["Url"].endswith("/acme1/exoml/start_voice/777") and "To" not in sent
    assert live["can_transfer"]
    r = owner.c.get(f"/api/v1/{_hook(owner, data, 'connect')}", query_string={"CallSid": "OUT1", "CallFrom": "09876543210", "CustomField": live["id"]})
    assert r.get_json()["destination"]["numbers"] == ["+919000000002"]


def test_exotel_refusing_a_call_shows_its_reason(app, exo):
    owner, _ = signup(app)
    _profile(owner, OWNER_PHONE)
    _connect(owner)
    lead = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "phone": CLIENT}).get_json()["data"]
    exo.refuse = "Call to unverified number is not allowed in trial account"
    r = owner.post("/api/v1/calling/call", json={"lead_id": lead["id"]})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "calling_refused"
    assert "unverified number" in r.get_json()["error"]["message"]
