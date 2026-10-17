import datetime as dt

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import FamilyMessage, Meeting
from app.models.base import utcnow
from app.services import family
from tests.test_phone_privacy import _member
from tests.test_realestate import _project
from tests.test_whatsapp import _connect, _hook, _inbound, meta  # noqa: F401  (pytest fixture)


def _lead_with_flat(cl):
    pid, tid = _project(cl)
    uid = cl.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]["floors"][0]["units"][0]["id"]
    lead = cl.post("/api/v1/leads", json={"first_name": "Ramesh", "last_name": "Gupta", "phone": "+91 98765 43210", "project_id": pid, "unit_id": uid}).get_json()["data"]
    return lead


def _add(cl, lead, **over):
    body = {"record": f"lead:{lead['id']}", "name": "Rohan Gupta", "relation": "son", "role": "pays", "phone": "+971 50 123 4567", "language": "hi",
            "timezone": "Asia/Dubai", "city": "Dubai", "is_nri": True, "currency": "AED", **over}
    r = cl.post("/api/v1/family", json=body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def test_time_zone_helpers():
    now = dt.datetime(2026, 10, 17, 18, 30, tzinfo=dt.timezone.utc)  # 10:30 pm in Dubai
    assert family.is_quiet(now.astimezone(family.zone("Asia/Dubai")))
    assert family.next_morning("Asia/Dubai", now) == dt.datetime(2026, 10, 18, 5, 0, tzinfo=dt.timezone.utc)  # 9 am Dubai
    early = dt.datetime(2026, 10, 17, 1, 0, tzinfo=dt.timezone.utc)  # 5 am Dubai: same day's 9 am
    assert family.next_morning("Asia/Dubai", early) == dt.datetime(2026, 10, 17, 5, 0, tzinfo=dt.timezone.utc)
    assert family.local_label(now, "America/New_York") == "Sat 17 Oct, 2:30 pm New York time"
    assert family.convert(20000000, "AED", {"AED": 22.7}) == 881057 and family.convert(None, "AED", {"AED": 22.7}) is None


def test_family_members_prices_and_checklist(client):
    lead = _lead_with_flat(client)
    son = _add(client, lead)
    assert son["relation_label"] == "Son" and son["language_label"] == "Hindi" and son["place"] == "Dubai"
    assert son["prices"][0]["inr_text"] == "₹2 Cr" and son["prices"][0]["amount"] is None  # no rate set yet: never a made-up price
    assert len(son["checklist"]) == len(family.CHECKLIST) and son["checklist_done"] == 0
    _add(client, lead, name="Sunita Gupta", relation="spouse", role="decides", phone=None, timezone="Asia/Kolkata", is_nri=False, currency="INR", language="mr")
    assert client.post("/api/v1/family", json={"record": f"lead:{lead['id']}", "name": "X", "language": "xx"}).status_code == 422
    assert client.post("/api/v1/family", json={"record": f"lead:{lead['id']}", "name": "X", "timezone": "Mars/Base"}).status_code == 422

    # the owner sets the rate; prices follow
    r = client.put("/api/v1/family/settings", json={"AED": 22.7, "USD": 83.4})
    assert r.status_code == 200 and r.get_json()["data"]["rates"] == {"AED": 22.7, "USD": 83.4}
    got = client.get("/api/v1/family", query_string={"record": f"lead:{lead['id']}"}).get_json()["data"]
    assert [m["name"] for m in got["members"]] == ["Rohan Gupta", "Sunita Gupta"]
    p = got["members"][0]["prices"][0]
    assert p["amount"] == 881057 and p["amount_text"] == "AED 881,057" and p["label"].startswith("Flat 301 · 3 BHK")
    assert got["members"][1]["checklist"] == []  # not NRI

    r = client.put(f"/api/v1/family/{son['id']}/checklist", json={"item": "poa", "done": True})
    assert r.get_json()["data"]["checklist_done"] == 1
    draft = client.post(f"/api/v1/family/{son['id']}/draft", json={"kind": "checklist"}).get_json()["data"]["text"]
    assert "Passport" in draft and "Power of attorney" not in draft
    draft = client.post(f"/api/v1/family/{son['id']}/draft", json={"kind": "prices"}).get_json()["data"]["text"]
    assert "₹2 Cr (about AED 881,057)" in draft and "₹22.7 per AED" in draft

    # after converting, the family is still on the client
    conv = client.post(f"/api/v1/leads/{lead['id']}/convert", json={"create_deal": True, "deal_name": "Flat 301", "deal_value": 20000000}).get_json()["data"]
    assert len(client.get("/api/v1/family", query_string={"record": f"contact:{conv['contact_id']}"}).get_json()["data"]["members"]) == 2
    assert len(client.get("/api/v1/family", query_string={"record": f"deal:{conv['deal_id']}"}).get_json()["data"]["members"]) == 2


def test_only_the_owner_sets_rates_and_reps_see_masked_numbers(app):
    from tests.conftest import signup

    owner, _ = signup(app)
    lead = _lead_with_flat(owner)
    son = _add(owner, lead)
    assert son["phone"] == "+971 50 123 4567"
    admin = _member(app, owner, "admin", "admin@acme.io")
    assert admin.put("/api/v1/family/settings", json={"AED": 23}).status_code == 403
    rep = _member(app, owner, "sales_rep", "rep@acme.io")
    got = rep.get("/api/v1/family", query_string={"record": f"lead:{lead['id']}"}).get_json()["data"]["members"][0]
    assert got["phone_masked"] is True and "4567" not in got["phone"]
    assert rep.post(f"/api/v1/family/{son['id']}/reveal-phone").status_code == 403
    # a masked number in an edit keeps the saved one; a new number over it is refused
    assert rep.patch(f"/api/v1/family/{son['id']}", json={"phone": got["phone"], "city": "Abu Dhabi"}).status_code == 200
    assert rep.patch(f"/api/v1/family/{son['id']}", json={"phone": "+971 50 000 0000"}).status_code == 403
    mgr = _member(app, owner, "manager", "mgr@acme.io")
    assert mgr.post(f"/api/v1/family/{son['id']}/reveal-phone").get_json()["data"]["phone"] == "+971 50 123 4567"
    logs = owner.get("/api/v1/audit-logs").get_json()["data"]
    assert any(l["action"] == "phone.revealed" and "Rohan Gupta" in l["summary"] for l in logs)


def test_messages_in_their_language_and_time_zone(client, meta, monkeypatch):  # noqa: F811
    _connect(client)
    lead = _lead_with_flat(client)
    son = _add(client, lead)

    # no AI key: the text comes back as typed, and says so
    out = client.post(f"/api/v1/family/{son['id']}/translate", json={"text": "Hi Rohan, the flat is ready to see."}).get_json()["data"]
    assert out["ai"] is False and out["text"] == "Hi Rohan, the flat is ready to see." and "AI key" in out["note"]

    # with a key the workspace's AI translates it
    from app.services.ai import assistant, settings as ai_settings

    real = ai_settings.resolve
    monkeypatch.setattr(ai_settings, "resolve", lambda wid=None: ai_settings.AIConfig(provider="openai", key="k", source="workspace") if wid is None else real(wid))
    monkeypatch.setattr(assistant, "structured", lambda kind, prompt, ctx, feature, **kw: {"text": "नमस्ते रोहन, फ्लैट देखने के लिए तैयार है।"} if "into Hindi" in prompt else {})
    out = client.post(f"/api/v1/family/{son['id']}/translate", json={"text": "Hi Rohan, the flat is ready to see."}).get_json()["data"]
    assert out["ai"] is True and out["text"].startswith("नमस्ते")

    # free text needs their 24-hour window; outside it a template goes out
    r = client.post(f"/api/v1/family/{son['id']}/messages", json={"text": out["text"]})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "whatsapp_window_closed"
    r = client.post(f"/api/v1/family/{son['id']}/messages", json={"template": {"name": "visit_named", "language": "en", "params": ["Rohan", "Victory Valley"]}})
    assert r.status_code == 201, r.get_json()
    assert meta.messages[-1]["to"] == "971501234567"

    # their reply goes on the buyer's timeline, not into a new lead
    assert _hook(client, _inbound("wamid.FAM1", "971501234567", "Papa ko dikha do", name="Rohan")).status_code == 200
    assert len(client.get("/api/v1/leads").get_json()["data"]) == 1
    tl = client.get(f"/api/v1/timeline?entity=lead&id={lead['id']}").get_json()["data"]
    assert any(a["title"] == "WhatsApp reply from Rohan Gupta (son of Ramesh Gupta)" for a in tl)
    # and stays out of the buyer's own chat
    assert client.get(f"/api/v1/whatsapp/conversation?lead_id={lead['id']}").get_json()["data"]["messages"] == []

    r = client.post(f"/api/v1/family/{son['id']}/messages", json={"text": out["text"], "original": "Hi Rohan, the flat is ready to see."})
    assert r.status_code == 201 and meta.messages[-1]["text"]["body"].startswith("नमस्ते")
    conv = client.get(f"/api/v1/family/{son['id']}/messages").get_json()["data"]
    assert conv["window_open"] is True and [m["direction"] for m in conv["messages"]] == ["outbound", "inbound", "outbound"]

    # held until 9 am in Dubai, then sent by the job
    r = client.post(f"/api/v1/family/{son['id']}/messages", json={"text": "Good morning!", "when": "morning"})
    assert r.status_code == 201 and r.get_json()["data"]["status"] == "scheduled" and "Dubai time" in r.get_json()["data"]["local_label"]
    sent_before = len(meta.messages)
    with client.app.app_context(), bypass_scope():
        fm = db.session.get(FamilyMessage, r.get_json()["data"]["id"])
        fm.send_at = utcnow() - dt.timedelta(minutes=1)
        db.session.commit()
        assert family.send_due() == {"sent": 1, "failed": 0}
    assert len(meta.messages) == sent_before + 1 and meta.messages[-1]["text"]["body"] == "Good morning!"


def test_walkthrough_from_their_page_confirmed_with_a_link(client, meta):  # noqa: F811
    lead = _lead_with_flat(client)
    son = _add(client, lead)
    client.put("/api/v1/family/settings", json={"AED": 22.7})
    link = client.post(f"/api/v1/family/{son['id']}/link").get_json()["data"]["link"]
    token = link.rsplit("/", 1)[-1]

    anon = client.app.test_client()
    page = anon.get(f"/api/v1/public/family/{token}").get_json()["data"]
    assert page["member"] == {"first_name": "Rohan", "timezone": "Asia/Dubai", "place": "Dubai", "currency": "AED", "is_nri": True}
    assert page["project"]["name"] == "Ireo Victory Valley" and page["prices"][0]["amount_text"] == "AED 881,057"
    assert "phone" not in str(page) and len(page["checklist"]) == len(family.CHECKLIST)
    assert anon.get("/api/v1/public/family/not-a-real-token-at-all").status_code == 404

    day = (utcnow() + dt.timedelta(days=3)).astimezone(family.zone("Asia/Dubai")).date()
    r = anon.post(f"/api/v1/public/family/{token}/walkthrough", json={"starts_at": f"{day}T19:30", "note": "Papa will join from Pune"})
    assert r.status_code == 201, r.get_json()
    w = r.get_json()["data"]["walkthroughs"][0]
    assert w["status"] == "requested" and w["local_label"].endswith("7:30 pm Dubai time") and w["meeting_url"] is None
    assert anon.post(f"/api/v1/public/family/{token}/walkthrough", json={"starts_at": "2020-01-01T10:00"}).status_code == 422

    member = client.get("/api/v1/family", query_string={"record": f"lead:{lead['id']}"}).get_json()["data"]["members"][0]
    wid = member["walkthroughs"][0]["id"]
    assert client.post(f"/api/v1/family/walkthroughs/{wid}/confirm", json={"meeting_url": "http://insecure"}).status_code == 422
    r = client.post(f"/api/v1/family/walkthroughs/{wid}/confirm", json={"meeting_url": "https://meet.google.com/abc-defg-hij"})
    out = r.get_json()["data"]
    assert r.status_code == 200 and out["walkthrough"]["status"] == "confirmed"
    assert out["sent"] is False and "Connect WhatsApp" in out["reason"]  # still confirmed; the rep copies the message
    assert "7:30 pm Dubai time" in out["message"] and "https://meet.google.com/abc-defg-hij" in out["message"]
    with client.app.app_context(), bypass_scope():
        mt = db.session.query(Meeting).one()
        assert mt.meeting_url == "https://meet.google.com/abc-defg-hij" and str(mt.lead_id) == lead["id"]
    page = anon.get(f"/api/v1/public/family/{token}").get_json()["data"]
    assert page["walkthroughs"][0]["meeting_url"] == "https://meet.google.com/abc-defg-hij"

    # removing the member closes their page
    assert client.delete(f"/api/v1/family/{son['id']}").status_code == 204
    assert anon.get(f"/api/v1/public/family/{token}").status_code == 404
