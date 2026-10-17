import datetime as dt
import time

import pytest

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import Lead, Notification, WhatsAppMessage
from app.services import whatsapp_crm
from app.services.ai import settings as ai_settings
from tests.test_phone_privacy import _member
from tests.test_realestate import _project
from tests.test_whatsapp import FakeMeta, _connect, _hook, _inbound

REP_PHONE = "919811122233"


@pytest.fixture()
def meta(monkeypatch):
    m = FakeMeta()
    media_get = m.get

    def get(url, params=None, headers=None, **kw):  # voice notes: media id -> download url -> bytes
        if url.endswith("/MEDIA_VOICE"):
            return m._r(200, {"url": "https://lookaside.fbsbx.com/voice", "mime_type": "audio/ogg"})
        if url == "https://lookaside.fbsbx.com/voice":
            import httpx
            return httpx.Response(200, content=b"OggS fake", request=httpx.Request("GET", url))
        return media_get(url, params=params, headers=headers, **kw)

    monkeypatch.setattr("httpx.get", get)
    monkeypatch.setattr("httpx.post", m.post)
    return m


def _msg(phone, wamid, **body):
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": "PNID"}, "contacts": [{"wa_id": phone, "profile": {"name": "Rep"}}],
        "messages": [{"from": phone, "id": wamid, "timestamp": str(int(time.time())), **body}]}}]}]}


def _say(cl, text, n=[0]):
    n[0] += 1
    return _hook(cl, _inbound(f"wamid.REP{n[0]}{time.time_ns()}", REP_PHONE, text))


def _tap(cl, button_id):
    return _hook(cl, _msg(REP_PHONE, f"wamid.TAP{time.time_ns()}", type="interactive",
                          interactive={"type": "button_reply", "button_reply": {"id": button_id, "title": "x"}}))


def _last(meta):
    return meta.messages[-1]


def _text(msg):
    return msg["text"]["body"] if msg["type"] == "text" else msg["interactive"]["body"]["text"] if msg["type"] == "interactive" else str(msg)


def _linked_rep(app, owner, meta):
    """A sales rep who has linked their WhatsApp number."""
    _connect(owner)
    rep = _member(app, owner, "sales_rep", "rep@acme.io")
    rep.patch("/api/v1/me/preferences", json={"phone": "+91 98111 22233"})
    v = rep.post("/api/v1/whatsapp/me/link").get_json()["data"]
    assert v["available"] and v["link"]["message"].startswith("LINK ") and v["company_number"] == "+919999900000"
    assert v["link"]["wa_url"].startswith("https://wa.me/919999900000?text=LINK")
    assert _say(owner, v["link"]["message"]).status_code == 200
    return rep


def test_link_number_then_messages_are_the_reps_not_leads(app, client, meta):
    rep = _linked_rep(app, client, meta)
    assert "Linked" in _text(_last(meta)) and _last(meta)["to"] == REP_PHONE
    me = rep.get("/api/v1/whatsapp/me").get_json()["data"]
    assert me["linked"] and me["link"] is None and not me["morning_plan"]
    _say(client, "hi")
    assert "Visited Priya" in _text(_last(meta))  # help
    assert client.get("/api/v1/leads").get_json()["data"] == []  # the rep never became a lead
    with app.app_context(), bypass_scope():
        rows = db.session.query(WhatsAppMessage).filter_by(phone=REP_PHONE).all()
        assert rows and all(r.lead_id is None and r.contact_id is None and r.data.get("rep") for r in rows)

    # changing the profile phone unlinks: only the number on the account counts
    rep.patch("/api/v1/me/preferences", json={"phone": "+91 90000 11111"})
    assert not rep.get("/api/v1/whatsapp/me").get_json()["data"]["linked"]
    _say(client, "hello again")
    assert client.get("/api/v1/leads").get_json()["data"][0]["source"] == "whatsapp"


def test_code_from_another_number_does_not_link(app, client, meta):
    _connect(client)
    rep = _member(app, client, "sales_rep", "rep@acme.io")
    rep.patch("/api/v1/me/preferences", json={"phone": "+91 98111 22233"})
    code = rep.post("/api/v1/whatsapp/me/link").get_json()["data"]["link"]["message"]
    _hook(client, _inbound("wamid.X1", "919000000009", code))
    assert "doesn't match" in _text(_last(meta))
    assert not rep.get("/api/v1/whatsapp/me").get_json()["data"]["linked"]
    assert client.get("/api/v1/leads").get_json()["data"] == []
    # a wrong code is just a client message
    _hook(client, _inbound("wamid.X2", "919000000008", "LINK 000000"))
    assert len(client.get("/api/v1/leads").get_json()["data"]) == 1


def test_visit_update_needs_confirm_then_saves_as_the_rep_with_undo(app, client, meta):
    rep = _linked_rep(app, client, meta)
    pid, _ = _project(client)
    lead = client.post("/api/v1/leads", json={"first_name": "Priya", "last_name": "Sharma", "phone": "9876500001", "project_id": pid}).get_json()["data"]
    _say(client, "Visited Priya, liked 301, follow up Sunday, budget 2.2 cr")
    card = _last(meta)
    assert card["type"] == "interactive" and "Log site visit with Priya Sharma" in _text(card)
    ok_id, no_id = [b["reply"]["id"] for b in card["interactive"]["action"]["buttons"]]
    assert ok_id.startswith("wacrm:ok:") and no_id.startswith("wacrm:no:")
    assert client.get("/api/v1/meetings", query_string={"lead_id": lead["id"]}).get_json()["data"] == []  # nothing saved yet

    _tap(client, ok_id)
    done = _last(meta)
    assert "Saved" in _text(done) and f"/app/leads/{lead['id']}" in _text(done)
    visits = client.get("/api/v1/meetings", query_string={"lead_id": lead["id"]}).get_json()["data"]
    assert visits and visits[0]["kind"] == "site_visit"
    got = client.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]
    assert float(got["budget_max"]) == 22000000 and got["next_follow_up_at"]
    audit = client.get("/api/v1/audit-logs").get_json()["data"]
    assert any("(via WhatsApp)" in (a["actor_label"] or "") for a in audit)

    _tap(client, ok_id)  # a second tap doesn't save twice
    assert "already saved" in _text(_last(meta))
    assert len(client.get("/api/v1/meetings", query_string={"lead_id": lead["id"]}).get_json()["data"]) == 1
    assert done["type"] == "text"  # sales reps can't delete, so no Undo button that would fail


def test_owner_can_undo_from_whatsapp(app, client, meta):
    _connect(client)
    client.patch("/api/v1/me/preferences", json={"phone": "+91 98111 22233"})
    _say(client, client.post("/api/v1/whatsapp/me/link").get_json()["data"]["link"]["message"])
    lead = client.post("/api/v1/leads", json={"first_name": "Farah", "last_name": "Khan"}).get_json()["data"]
    _say(client, "Called Farah, interested, call back tomorrow")
    _tap(client, _last(meta)["interactive"]["action"]["buttons"][0]["reply"]["id"])
    assert len(client.get("/api/v1/calls", query_string={"lead_id": lead["id"]}).get_json()["data"]) == 1
    _tap(client, _last(meta)["interactive"]["action"]["buttons"][0]["reply"]["id"])
    assert "Undone" in _text(_last(meta))
    assert client.get("/api/v1/calls", query_string={"lead_id": lead["id"]}).get_json()["data"] == []
    assert client.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]["next_follow_up_at"] is None


def test_cancel_and_ambiguous_names(app, client, meta):
    _linked_rep(app, client, meta)
    a = client.post("/api/v1/leads", json={"first_name": "Rahul", "last_name": "Mehta"}).get_json()["data"]
    client.post("/api/v1/leads", json={"first_name": "Rahul", "last_name": "Verma"})
    _say(client, "Called Rahul, call back tomorrow")
    assert "Which one did you mean?" in _text(_last(meta)) and "Rahul Verma" in _text(_last(meta))
    _say(client, "Called Rahul Mehta, call back tomorrow")
    card = _last(meta)
    assert "Log call with Rahul Mehta" in _text(card)
    _tap(client, card["interactive"]["action"]["buttons"][1]["reply"]["id"])
    assert "Nothing was saved" in _text(_last(meta))
    assert client.get("/api/v1/calls", query_string={"lead_id": a["id"]}).get_json()["data"] == []


def test_new_lead_from_whatsapp_text_is_owned_by_the_rep(app, client, meta):
    rep = _linked_rep(app, client, meta)
    _say(client, "New lead Neha Kapoor 98765 43219, 3 BHK in Baner, budget 1.5 cr")
    card = _last(meta)
    assert "Neha" in _text(card) and "•••19" in _text(card)  # a sales rep doesn't see client numbers, even on WhatsApp
    _tap(client, card["interactive"]["action"]["buttons"][0]["reply"]["id"])
    me = rep.get("/api/v1/auth/me").get_json()["data"]["user"]["id"]
    lead = client.get("/api/v1/leads").get_json()["data"][0]
    assert lead["first_name"] == "Neha" and lead["owner_id"] == me and lead["phone"].endswith("43219")


def test_voice_notes_need_an_audio_key(app, client, meta, monkeypatch):
    _linked_rep(app, client, meta)
    voice = dict(type="audio", audio={"id": "MEDIA_VOICE", "mime_type": "audio/ogg; codecs=opus", "voice": True})
    _hook(client, _msg(REP_PHONE, "wamid.V1", **voice))
    assert "send the update as text" in _text(_last(meta))

    from app.services.ai import features
    monkeypatch.setitem(ai_settings.PROVIDERS, "mock", {"audio": True})
    heard = {}
    monkeypatch.setattr(features, "transcribe", lambda audio, name, mime: heard.update(audio=audio, mime=mime) or "Visited Anil, liked 302, follow up tomorrow")
    client.post("/api/v1/leads", json={"first_name": "Anil", "last_name": "Kumar"})
    _hook(client, _msg(REP_PHONE, "wamid.V2", **voice))
    assert heard == {"audio": b"OggS fake", "mime": "audio/ogg"}
    assert "I heard" in _text(_last(meta)) and "Log site visit with Anil Kumar" in _text(_last(meta))


def test_lead_alerts_and_morning_plan(app, client, meta):
    rep = _linked_rep(app, client, meta)
    rep_id = rep.get("/api/v1/auth/me").get_json()["data"]["user"]["id"]
    rep.patch("/api/v1/whatsapp/me", json={"new_leads": True, "morning_plan": True})
    _say(client, "alerts on")
    assert "Turned on" in _text(_last(meta))
    lead = client.post("/api/v1/leads", json={"first_name": "Kiran", "last_name": "Rao", "bhk": "2 BHK", "phone": "9876500002", "owner_id": rep_id,
                                              "next_follow_up_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()}).get_json()["data"]
    with app.app_context(), bypass_scope():
        assert whatsapp_crm.send_lead_alerts()["sent"] == 1
        assert whatsapp_crm.send_lead_alerts()["sent"] == 0  # once per lead
    alert = _text(_last(meta))
    assert "New lead: Kiran Rao" in alert and "2 BHK" in alert and lead["id"] in alert and "9876500002" not in alert

    # morning plan at 9 AM India time, once a day
    nine = dt.datetime.now(dt.timezone.utc).replace(hour=3, minute=35)  # 09:05 IST
    with app.app_context(), bypass_scope():
        assert whatsapp_crm.send_morning_plans(nine)["sent"] == 1
        assert whatsapp_crm.send_morning_plans(nine + dt.timedelta(minutes=15))["sent"] == 0
        assert whatsapp_crm.send_morning_plans(nine - dt.timedelta(hours=1))["sent"] == 0
    plan = _text(_last(meta))
    assert "Good morning" in plan and "Kiran Rao" in plan

    # outside WhatsApp's 24-hour window an approved template is needed
    with app.app_context(), bypass_scope():
        db.session.query(WhatsAppMessage).filter_by(phone=REP_PHONE, direction="inbound").update(
            {"created_at": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)})
        db.session.commit()
    client.post("/api/v1/leads", json={"first_name": "Meera", "owner_id": rep_id})
    with app.app_context(), bypass_scope():
        assert whatsapp_crm.send_lead_alerts()["skipped"] == 1
        assert db.session.query(Notification).filter(Notification.title.like("New lead: Meera%")).one().data["wa"] == "no_template"
    assert client.patch("/api/v1/whatsapp/team-settings", json={"team_template": "visit_named|en"}).status_code == 422  # two placeholders
    assert rep.patch("/api/v1/whatsapp/team-settings", json={"team_template": None}).status_code == 403
    from tests import test_whatsapp
    test_whatsapp.TEMPLATES.append({"name": "team_alert", "language": "en", "status": "APPROVED", "category": "UTILITY", "components": [{"type": "BODY", "text": "CRM Wala: {{1}}"}]})
    try:
        assert client.patch("/api/v1/whatsapp/team-settings", json={"team_template": "team_alert|en"}).status_code == 200
        client.post("/api/v1/leads", json={"first_name": "Zoya", "owner_id": rep_id})
        with app.app_context(), bypass_scope():
            assert whatsapp_crm.send_lead_alerts()["template"] == 1
    finally:
        test_whatsapp.TEMPLATES.pop()
    t = _last(meta)
    assert t["type"] == "template" and t["template"]["name"] == "team_alert"
    assert "New lead: Zoya" in t["template"]["components"][0]["parameters"][0]["text"] and "\n" not in t["template"]["components"][0]["parameters"][0]["text"]
    assert rep.get("/api/v1/whatsapp/me").get_json()["data"]["alert_template"]


def test_turn_off_and_unlink(app, client, meta):
    rep = _linked_rep(app, client, meta)
    rep.patch("/api/v1/whatsapp/me", json={"new_leads": True, "morning_plan": True})
    _say(client, "stop")
    v = rep.get("/api/v1/whatsapp/me").get_json()["data"]
    assert not v["new_leads"] and not v["morning_plan"]
    assert not rep.delete("/api/v1/whatsapp/me").get_json()["data"]["linked"]
    _say(client, "Visited someone")
    with app.app_context(), bypass_scope():
        assert db.session.query(Lead).count() == 1  # unlinked: back to being an ordinary sender
