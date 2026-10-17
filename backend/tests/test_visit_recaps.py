import io

import pytest

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import Notification, Task, Unit, VisitRecap
from tests.conftest import signup
from tests.test_realestate import _project
from tests.test_whatsapp import FakeMeta, _connect, _hook, _inbound, _upload


@pytest.fixture()
def meta(monkeypatch):
    from app.services import whatsapp

    m = FakeMeta()
    monkeypatch.setattr(whatsapp.httpx, "get", m.get)
    monkeypatch.setattr(whatsapp.httpx, "post", m.post)
    return m


def _flats(cl, n=3):
    pid, tid = _project(cl)
    units = [u for f in cl.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]["floors"] for u in f["units"]][:n]
    cl.patch(f"/api/v1/units/{units[1]['id']}", json={"sale_price": 18000000, "area_sqft": 2000, "facing": "East"})
    return pid, [u["id"] for u in units]


def _visit(cl, lead_id, unit_id=None, project_id=None):
    r = cl.post("/api/v1/meetings", json={"title": "Site visit", "kind": "site_visit", "starts_at": "2026-10-17T10:00:00+05:30", "ends_at": "2026-10-17T11:00:00+05:30",
                                          "lead_id": lead_id, "unit_id": unit_id, "project_id": project_id})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def _photo(cl, name="balcony.jpg", **form):
    r = cl.c.post("/api/v1/files", data={"file": (io.BytesIO(b"\xff\xd8\xff\xe0 fake jpeg"), name, "image/jpeg"), **form}, headers=cl._h(), content_type="multipart/form-data")
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]


def _lead(cl, phone="+91 98765 43210"):
    return cl.post("/api/v1/leads", json={"first_name": "Rohit", "last_name": "Sharma", "phone": phone}).get_json()["data"]


def test_recap_from_a_visit_and_the_public_page(client):
    pid, ids = _flats(client)
    lead = _lead(client)
    m = _visit(client, lead["id"], unit_id=ids[0])
    client.patch(f"/api/v1/meetings/{m['id']}", json={"status": "completed"})

    # with no flats given, it starts from the flat booked for the visit, and the message is pre-written
    r = client.post("/api/v1/visit-recaps", json={"meeting_id": m["id"]})
    assert r.status_code == 201, r.get_json()
    rec = r.get_json()["data"]
    assert [f["id"] for f in rec["flats"]] == [ids[0]] and rec["lead_id"] == lead["id"] and rec["buyer"]["name"] == "Rohit Sharma"
    assert rec["message"].startswith("Hi Rohit, thank you for visiting Ireo Victory Valley today") and "token" not in rec
    token = rec["url"].rsplit("/v/", 1)[1]
    assert len(token) >= 30

    # the rep adds flats and photos; posting again for the same visit keeps the same link
    photo = _photo(client, lead_id=lead["id"])
    brochure = _upload(client, "Victory Valley price list.pdf", project_id=pid, doc_kind="price_list")
    secret = _upload(client, "internal margins.pdf", project_id=pid)  # not a brochure / price list: never public
    r = client.post("/api/v1/visit-recaps", json={"meeting_id": m["id"], "unit_ids": ids[:2], "photo_ids": [photo["id"]], "message": "Hi Rohit, here you go."})
    assert r.status_code == 200 and r.get_json()["data"]["url"] == rec["url"]
    assert client.post("/api/v1/visit-recaps", json={"meeting_id": m["id"], "photo_ids": [brochure["id"]]}).status_code == 422  # a PDF isn't a photo

    # the family opens it with no login
    anon = client.app.test_client()
    page = anon.get(f"/api/v1/public/recaps/{token}")
    assert page.status_code == 200, page.get_json()
    d = page.get_json()["data"]
    assert d["buyer_first_name"] == "Rohit" and d["message"] == "Hi Rohit, here you go." and d["project"]["name"] == "Ireo Victory Valley"
    assert [f["id"] for f in d["flats"]] == ids[:2] and d["flats"][1]["price"] == "₹1.8 Cr" and d["flats"][1]["facing"] == "East"
    assert d["comparison"]["rows"] and d["photos"] == [photo["id"]] and d["has_price_list"] is True
    assert [x["id"] for x in d["documents"]] == [brochure["id"]]
    assert "phone" not in str(d) and "98765" not in str(d)
    assert anon.get(f"/api/v1/public/recaps/{token}/files/{photo['id']}").status_code == 200
    assert anon.get(f"/api/v1/public/recaps/{token}/files/{brochure['id']}").status_code == 200
    assert anon.get(f"/api/v1/public/recaps/{token}/files/{secret['id']}").status_code == 404
    assert anon.get("/api/v1/public/recaps/" + "x" * 32).status_code == 404
    assert anon.get(f"/api/v1/public/recaps/{token}?meta=1").status_code == 200
    with client.app.app_context(), bypass_scope():
        assert db.session.query(VisitRecap).one().views == 1  # link previews don't count

    # switched off: the link stops working
    assert client.post(f"/api/v1/visit-recaps/{rec['id']}/revoke").status_code == 200
    assert anon.get(f"/api/v1/public/recaps/{token}").status_code == 404


def test_hold_request_tells_the_rep_and_leaves_the_flat_alone(client):
    _, ids = _flats(client)
    lead = _lead(client)
    rec = client.post("/api/v1/visit-recaps", json={"lead_id": lead["id"], "unit_ids": ids[:2]}).get_json()["data"]
    token = rec["url"].rsplit("/v/", 1)[1]
    anon = client.app.test_client()
    r = anon.post(f"/api/v1/public/recaps/{token}/hold", json={"unit_id": ids[1], "name": "Rohit's father", "note": "We like the east facing one"})
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "requested"
    assert anon.post(f"/api/v1/public/recaps/{token}/hold", json={"unit_id": ids[1]}).get_json()["data"]["status"] == "already_requested"
    assert anon.post(f"/api/v1/public/recaps/{token}/hold", json={"unit_id": ids[2]}).status_code == 404  # not on this recap
    with client.app.app_context(), bypass_scope():
        assert db.session.get(Unit, ids[1]).status == "vacant"  # only a request
        task = db.session.query(Task).filter(Task.title.like("Hold request%")).one()
        assert task.priority == "urgent" and str(task.lead_id) == lead["id"] and "Flat 302" in task.title
        assert db.session.query(Notification).filter(Notification.title.like("Rohit's father asked you to hold Flat 302%")).count() == 1
    assert anon.get(f"/api/v1/public/recaps/{token}").get_json()["data"]["flats"][1]["hold_requested"] is True
    tl = client.get(f"/api/v1/timeline?entity=lead&id={lead['id']}").get_json()["data"]
    assert any(a["title"].startswith("Rohit's father asked you to hold") for a in tl)

    # a flat that got booked can't be asked for
    client.patch(f"/api/v1/units/{ids[0]}", json={"status": "booked"})
    assert anon.post(f"/api/v1/public/recaps/{token}/hold", json={"unit_id": ids[0]}).status_code == 409
    assert anon.get(f"/api/v1/public/recaps/{token}").get_json()["data"]["flats"][0]["can_hold"] is False


def test_send_without_whatsapp_business_gives_a_link_and_hides_the_number_from_reps(client):
    _, ids = _flats(client)
    lead = _lead(client)
    rec = client.post("/api/v1/visit-recaps", json={"lead_id": lead["id"], "unit_ids": ids[:1]}).get_json()["data"]
    r = client.post(f"/api/v1/visit-recaps/{rec['id']}/send")
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert d["status"] == "link" and d["whatsapp_url"].startswith("https://wa.me/919876543210?text=")  # the owner may see the number
    assert d["recap"]["sent_via"] == "whatsapp_link" and d["recap"]["sent_at"]

    # a sales rep gets the same link without the number
    from tests.test_phone_privacy import _member

    rep = _member(client.app, client, "sales_rep", "rep@acme.io")
    d = rep.post(f"/api/v1/visit-recaps/{rec['id']}/send").get_json()["data"]
    assert d["whatsapp_url"].startswith("https://wa.me/?text=") and "98765" not in str(d)


def test_send_through_whatsapp_business(client, meta):
    _connect(client)
    _, ids = _flats(client)
    lead = _lead(client)
    rec = client.post("/api/v1/visit-recaps", json={"lead_id": lead["id"], "unit_ids": ids[:2]}).get_json()["data"]

    # outside the 24h window and no recap template yet: falls back to a link, with the reason
    d = client.post(f"/api/v1/visit-recaps/{rec['id']}/send").get_json()["data"]
    assert d["status"] == "link" and "24 hours" in d["reason"] and not meta.messages

    # the recap template: first name, then the link
    assert client.patch("/api/v1/whatsapp/settings", json={"recap_template": "site_visit_reminder|en"}).status_code == 422  # 3 placeholders
    assert client.patch("/api/v1/whatsapp/settings", json={"media_template": "property_brochure|en"}).status_code == 200
    s = client.patch("/api/v1/whatsapp/settings", json={"recap_template": "visit_named|en"}).get_json()["data"]
    assert s["recap_template"]["name"] == "visit_named" and s["media_template"]["name"] == "property_brochure"  # one doesn't clear the other
    d = client.post(f"/api/v1/visit-recaps/{rec['id']}/send").get_json()["data"]
    assert d["status"] == "sent" and meta.messages[-1]["to"] == "919876543210"
    params = meta.messages[-1]["template"]["components"][0]["parameters"]
    assert params[0]["text"] == "Rohit" and params[1]["text"] == rec["url"]

    # inside the window it's a plain message with the link
    _hook(client, _inbound("wamid.IN9", "919876543210", "Thanks for today"))
    d = client.post(f"/api/v1/visit-recaps/{rec['id']}/send").get_json()["data"]
    assert d["status"] == "sent" and meta.messages[-1]["type"] == "text" and meta.messages[-1]["text"]["body"].endswith(rec["url"])
    tl = client.get(f"/api/v1/timeline?entity=lead&id={lead['id']}").get_json()["data"]
    assert any(a["title"].startswith("Visit recap sent on WhatsApp (2 flats") for a in tl)

    # the buyer opening it shows on the timeline once
    anon = client.app.test_client()
    token = rec["url"].rsplit("/v/", 1)[1]
    anon.get(f"/api/v1/public/recaps/{token}")
    anon.get(f"/api/v1/public/recaps/{token}")
    tl = client.get(f"/api/v1/timeline?entity=lead&id={lead['id']}").get_json()["data"]
    assert len([a for a in tl if a["title"] == "Visit recap opened by the buyer"]) == 1


def test_recaps_stay_inside_their_workspace(client):
    _, ids = _flats(client)
    lead = _lead(client)
    rec = client.post("/api/v1/visit-recaps", json={"lead_id": lead["id"], "unit_ids": ids[:1]}).get_json()["data"]
    other, _ = signup(client.app, email="b@other.io", company_name="Other")
    assert other.get(f"/api/v1/visit-recaps/{rec['id']}").status_code == 404
    assert other.post(f"/api/v1/visit-recaps/{rec['id']}/send").status_code == 404
    assert other.post("/api/v1/visit-recaps", json={"lead_id": lead["id"], "unit_ids": ids[:1]}).status_code == 422
    other_lead = _lead(other)
    assert other.post("/api/v1/visit-recaps", json={"lead_id": other_lead["id"], "unit_ids": ids[:1]}).status_code == 404  # someone else's flat
    assert client.post("/api/v1/visit-recaps", json={"unit_ids": ids[:1]}).status_code == 422  # no buyer
