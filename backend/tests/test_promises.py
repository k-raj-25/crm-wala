import uuid

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import AuditLog, Notification, Promise, WhatsAppMessage
from app.services.ai.extract import promises_from_text
from tests.conftest import signup
from tests.test_phone_privacy import _member
from tests.test_realestate import _project


def _lead(cl, **kw):
    return cl.post("/api/v1/leads", json={"first_name": "Priya", "last_name": "Nair", "phone": "+91 98765 43210", **kw}).get_json()["data"]


def test_rep_records_a_promise_and_a_manager_approves_it(app):
    owner, _ = signup(app)
    rep = _member(app, owner, "sales_rep", "rahul@acme.io")
    manager = _member(app, owner, "manager", "meena@acme.io")
    lead = _lead(owner)

    r = rep.post("/api/v1/promises", json={"lead_id": lead["id"], "title": "Free covered parking", "kind": "parking", "value": 300000})
    assert r.status_code == 201, r.get_json()
    p = r.get_json()["data"]
    assert p["status"] == "pending" and p["promised_by_name"] == "Rahul" and p["buyer_name"] == "Priya Nair" and p["source"] == "manual"

    # reps can't approve their own promises; managers are told there's one waiting
    assert rep.post(f"/api/v1/promises/{p['id']}/approve").status_code == 403
    with app.app_context(), bypass_scope():
        titles = [n.title for n in db.session.query(Notification).filter_by(type="promise")]
    assert "Rahul promised Priya Nair: Free covered parking. Approve or reject?" in titles

    # still pending, so the rep can fix it
    assert rep.patch(f"/api/v1/promises/{p['id']}", json={"title": "Free covered parking (basement)"}).status_code == 200
    assert rep.patch(f"/api/v1/promises/{p['id']}", json={"lead_id": str(uuid.uuid4())}).status_code == 400

    r = manager.post(f"/api/v1/promises/{p['id']}/approve", json={"note": "OK, slot B-12"})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert d["status"] == "approved" and d["decided_by_name"] == "Meena" and d["decision_note"] == "OK, slot B-12"
    assert manager.post(f"/api/v1/promises/{p['id']}/reject").get_json()["error"]["code"] == "promise_decided"

    # once approved it can't be edited or deleted, only cancelled with a reason
    assert rep.patch(f"/api/v1/promises/{p['id']}", json={"title": "Two parkings"}).status_code == 409
    assert manager.delete(f"/api/v1/promises/{p['id']}").status_code == 409
    assert rep.post(f"/api/v1/promises/{p['id']}/cancel", json={"note": "x"}).status_code == 403
    assert manager.post(f"/api/v1/promises/{p['id']}/cancel").status_code == 422
    with app.app_context(), bypass_scope():
        row = db.session.query(AuditLog).filter_by(action="promise.approved").one()
        assert "Free covered parking (basement)" in row.summary and "Rahul" in row.summary

    summary = owner.get("/api/v1/promises/summary").get_json()["data"]
    assert summary["counts"]["approved"] == 1 and summary["can_approve"] is True
    assert rep.get("/api/v1/promises/summary").get_json()["data"]["can_approve"] is False


def test_rejected_and_cancelled(client):
    lead = _lead(client)
    a = client.post("/api/v1/promises", json={"lead_id": lead["id"], "title": "Extra discount of 5 lakh", "kind": "discount"}).get_json()["data"]
    b = client.post("/api/v1/promises", json={"lead_id": lead["id"], "title": "Free AC"}).get_json()["data"]
    assert client.post(f"/api/v1/promises/{a['id']}/reject", json={"note": "Too much"}).get_json()["data"]["status"] == "rejected"
    assert client.post(f"/api/v1/promises/{b['id']}/cancel").get_json()["data"]["status"] == "cancelled"
    assert client.post(f"/api/v1/promises/{b['id']}/approve").status_code == 409
    statuses = {p["title"]: p["status"] for p in client.get("/api/v1/promises", query_string={"record": f"lead:{lead['id']}"}).get_json()["data"]}
    assert statuses == {"Extra discount of 5 lakh": "rejected", "Free AC": "cancelled"}


def test_promise_needs_a_buyer_in_this_workspace(app):
    owner, _ = signup(app)
    other, _ = signup(app, email="b@other.io", company_name="Other")
    theirs = _lead(other)
    assert owner.post("/api/v1/promises", json={"title": "Free parking"}).status_code == 422
    assert owner.post("/api/v1/promises", json={"title": "Free parking", "lead_id": theirs["id"]}).status_code == 422
    p = other.post("/api/v1/promises", json={"title": "Free parking", "lead_id": theirs["id"]}).get_json()["data"]
    assert owner.get(f"/api/v1/promises/{p['id']}").status_code == 404
    assert owner.get("/api/v1/promises").get_json()["data"] == []


def test_promises_follow_the_buyer_from_lead_to_deal_and_print_on_the_booking_form(client):
    pid, tid = _project(client)
    unit = client.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]["floors"][3]["units"][0]
    client.patch(f"/api/v1/units/{unit['id']}", json={"sale_price": 12500000})
    lead = _lead(client, unit_id=unit["id"], project_id=pid)
    p = client.post("/api/v1/promises", json={"lead_id": lead["id"], "title": "Free modular kitchen", "kind": "fittings", "details": "Hettich fittings"}).get_json()["data"]
    assert p["unit_id"] == unit["id"] and p["unit_label"].startswith(unit["number"])
    client.post(f"/api/v1/promises/{p['id']}/approve")
    pending = client.post("/api/v1/promises", json={"lead_id": lead["id"], "title": "Free gym for life"}).get_json()["data"]

    conv = client.post(f"/api/v1/leads/{lead['id']}/convert", json={"create_deal": True, "deal_name": "Priya 1204", "deal_value": 12000000}).get_json()["data"]
    deal_id = conv["deal_id"]
    on_deal = client.get("/api/v1/promises", query_string={"record": f"deal:{deal_id}"}).get_json()["data"]
    assert {x["id"] for x in on_deal} == {p["id"], pending["id"]}
    later = client.post("/api/v1/promises", json={"deal_id": deal_id, "title": "Possession by Dec 2027", "kind": "possession"}).get_json()["data"]
    assert later["lead_id"] == lead["id"] and later["contact_id"] == conv["contact_id"]
    assert len(client.get("/api/v1/promises", query_string={"record": f"lead:{lead['id']}"}).get_json()["data"]) == 3
    assert len(client.get("/api/v1/promises", query_string={"record": f"contact:{conv['contact_id']}"}).get_json()["data"]) == 3
    assert {x["deal_id"] for x in client.get("/api/v1/promises", query_string={"deal_id": deal_id}).get_json()["data"]} == {deal_id}

    r = client.get("/api/v1/promises/booking-form", query_string={"record": f"deal:{deal_id}"})
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    assert "Booking form - Priya Nair.pdf" in r.headers["Content-Disposition"]
    assert client.get("/api/v1/promises/booking-form", query_string={"record": "deal:nope"}).status_code == 400


def test_booking_form_lists_only_approved_promises(app, monkeypatch):
    cl, _ = signup(app)
    lead = _lead(cl)
    ok_ = cl.post("/api/v1/promises", json={"lead_id": lead["id"], "title": "Free covered parking"}).get_json()["data"]
    cl.post(f"/api/v1/promises/{ok_['id']}/approve")
    cl.post("/api/v1/promises", json={"lead_id": lead["id"], "title": "Free gym for life"})
    seen = {}
    from app.services import promises as svc

    real = svc.serialize
    monkeypatch.setattr(svc, "serialize", lambda rows: seen.setdefault("titles", [r.title for r in rows]) and real(rows))
    assert cl.get("/api/v1/promises/booking-form", query_string={"record": f"lead:{lead['id']}"}).status_code == 200
    assert seen["titles"] == ["Free covered parking"]


def test_finder_reads_parking_and_discounts_but_not_questions():
    found = promises_from_text("Does it have parking?\nSir I will give you free covered parking and a modular kitchen, pakka.\n"
                               "Ok final: extra discount of 2 lakh if you book this week. Price is 1.2 Cr. We can do a 10:90 payment plan.")
    assert [(f["kind"], f["title"]) for f in found] == [("parking", "Free covered parking"), ("fittings", "Free modular kitchen"),
                                                        ("discount", "Discount of ₹2 L"), ("payment_plan", "10:90 payment plan")]
    assert found[2]["value"] == 200000
    assert promises_from_text("Floor rise is waived for you")[0]["title"] == "Floor rise charge waived"
    assert promises_from_text("What is the possession date?") == []


def test_scan_whatsapp_and_call_notes_proposes_cards_without_recording_anything(app):
    owner, me = signup(app)
    rep = _member(app, owner, "sales_rep", "rahul@acme.io")
    lead = _lead(owner)
    rep_id = rep.get("/api/v1/auth/me").get_json()["data"]["user"]["id"]
    with app.app_context(), bypass_scope():
        db.session.add(WhatsAppMessage(workspace_id=uuid.UUID(me["workspace"]["id"]), lead_id=uuid.UUID(lead["id"]), direction="outbound", status="sent", kind="text",
                                       phone="919876543210", body="Priya ji, free covered parking de denge, pakka. Call me on 98765 43210", user_id=uuid.UUID(rep_id)))
        db.session.commit()
    rep.post("/api/v1/calls", json={"lead_id": lead["id"], "direction": "outbound", "status": "completed", "notes": "She asked about possession. I said we will give 1 lakh discount."})

    r = rep.post("/api/v1/ai/promises/scan", json={"record": f"lead:{lead['id']}"})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    cards = {p["changes"][0]["to"]: p for p in d["proposals"]}
    assert set(cards) == {"Free covered parking", "Discount of ₹1 L"}
    parking = cards["Free covered parking"]
    assert parking["kind"] == "record_promise" and parking["ops"][0]["path"] == "/api/v1/promises"
    body = parking["ops"][0]["body"]
    assert body["source"] == "whatsapp" and body["lead_id"] == lead["id"]
    assert "43210" not in str(d)  # the rep can't see the buyer's number, even inside a quoted chat
    with app.app_context(), bypass_scope():
        assert db.session.query(Promise).count() == 0  # nothing is saved until someone approves a card

    # Approving the card is the browser running its op as the rep: the promise lands as pending, credited to who sent the message
    vals = {c["key"]: c["to"] for c in parking["changes"]}
    sent = {k: (vals[v[2:-2]] if isinstance(v, str) and v.startswith("{{") else v) for k, v in body.items()}
    p = rep.post("/api/v1/promises?via=ai", json=sent).get_json()["data"]
    assert p["status"] == "pending" and p["promised_by_name"] == "Rahul" and p["source_label"] == "WhatsApp"
    again = rep.post("/api/v1/ai/promises/scan", json={"record": f"lead:{lead['id']}"}).get_json()["data"]
    assert [c["changes"][0]["to"] for c in again["proposals"]] == ["Discount of ₹1 L"] and again["already_recorded"] == 1


def test_scan_pasted_text_and_chat_tool(client):
    lead = _lead(client)
    d = client.post("/api/v1/ai/promises/scan", json={"record": f"lead:{lead['id']}", "text": "Possession by March 2027, I assure you."}).get_json()["data"]
    assert [p["changes"][0]["to"] for p in d["proposals"]] == ["Possession by March 2027"]
    from app.services.ai import actions

    with client.app.test_request_context():
        assert "propose_record_promise" in actions.PROPOSERS and any(s["name"] == "propose_record_promise" for s in actions.SPECS)
