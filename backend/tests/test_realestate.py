import datetime as dt

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import Unit
from app.models.base import utcnow
from tests.conftest import signup


def _project(cl, floors=3, per_floor=2, **tower):
    pid = cl.post("/api/v1/projects", json={"name": "Ireo Victory Valley", "city": "Gurgaon", "sector": "Sector 67"}).get_json()["data"]["id"]
    r = cl.post(f"/api/v1/projects/{pid}/towers", json={"name": "Tower D-13", "floors": floors, "units_per_floor": per_floor, "bhk": "3 BHK",
                                                         "area_sqft": 1800, "sale_price": 20000000, **tower})
    assert r.status_code == 201, r.get_json()
    return pid, r.get_json()["data"]["id"]


def test_tower_generates_units_and_building_view(client):
    pid, tid = _project(client)
    b = client.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]
    assert [f["floor"] for f in b["floors"]] == [3, 2, 1, 0]  # top first, ground included
    assert [u["number"] for u in b["floors"][0]["units"]] == ["301", "302"]
    assert [u["number"] for u in b["floors"][-1]["units"]] == ["001", "002"]
    assert b["summary"]["total"] == 8 and b["summary"]["counts"] == {"vacant": 8} and b["summary"]["available"] == 8
    p = client.get(f"/api/v1/projects/{pid}").get_json()["data"]
    assert p["summary"]["total"] == 8 and p["towers"][0]["summary"]["total"] == 8


def test_status_change_hold_and_history(client):
    pid, tid = _project(client)
    uid = client.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]["floors"][0]["units"][0]["id"]
    r = client.post(f"/api/v1/units/{uid}/status", json={"status": "on_hold", "hold_hours": 24, "note": "Mr Mehta wants to think"})
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "on_hold" and r.get_json()["data"]["hold_until"]
    assert client.post(f"/api/v1/units/{uid}/status", json={"status": "nonsense"}).status_code == 422
    hist = client.get(f"/api/v1/units/{uid}/history").get_json()["data"]
    assert hist[0]["to_status"] == "on_hold" and hist[0]["note"].startswith("Mr Mehta")
    # a lapsed hold goes back to stock the next time anyone looks
    with client.app.app_context(), bypass_scope():
        db.session.query(Unit).filter_by(id=uid).update({"hold_until": utcnow() - dt.timedelta(hours=1)})
        db.session.commit()
    b = client.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]
    assert b["summary"]["counts"].get("on_hold") is None
    assert client.get(f"/api/v1/units/{uid}").get_json()["data"]["status"] == "for_sale"  # it has a price, so it returns as listed


def test_winning_a_deal_marks_the_flat_sold(client):
    pid, tid = _project(client)
    uid = client.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]["floors"][0]["units"][0]["id"]
    contact = client.post("/api/v1/contacts", json={"first_name": "Meera", "last_name": "Nair"}).get_json()["data"]["id"]
    stages = client.get("/api/v1/pipelines").get_json()["data"][0]["stages"]
    won = next(s for s in stages if s["kind"] == "won")
    deal = client.post("/api/v1/deals", json={"name": "Meera - 301", "unit_id": uid, "contact_id": contact, "value": 20000000}).get_json()["data"]
    assert deal["project_id"] == pid  # taken from the unit
    assert client.post(f"/api/v1/deals/{deal['id']}/move", json={"stage_id": won["id"]}).status_code == 200
    u = client.get(f"/api/v1/units/{uid}").get_json()["data"]
    assert u["status"] == "sold" and u["occupant_contact"]["name"] == "Meera Nair"


def test_matching_clients_and_homes(client):
    pid, tid = _project(client)
    uid = client.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]["floors"][0]["units"][0]["id"]
    client.patch(f"/api/v1/units/{uid}", json={"status": "for_sale"})
    fits = client.post("/api/v1/leads", json={"first_name": "Rohit", "intent": "buy", "bhk": "3 BHK", "budget_max": 22000000}).get_json()["data"]
    client.post("/api/v1/leads", json={"first_name": "Too", "last_name": "Poor", "intent": "buy", "bhk": "3 BHK", "budget_max": 5000000})
    client.post("/api/v1/leads", json={"first_name": "Wrong", "last_name": "Size", "intent": "buy", "bhk": "1 BHK", "budget_max": 30000000})
    client.post("/api/v1/leads", json={"first_name": "Renter", "intent": "rent", "budget_max": 50000})
    m = client.get(f"/api/v1/units/{uid}/matches").get_json()["data"]
    assert [x["name"] for x in m] == ["Rohit"] and "within budget" in m[0]["reasons"]
    homes = client.get(f"/api/v1/leads/{fits['id']}/matches").get_json()["data"]
    assert homes and homes[0]["status"] == "for_sale" and homes[0]["match"]["score"] > 0
    assert client.post("/api/v1/leads", json={"first_name": "Bad", "budget_min": 9, "budget_max": 1}).status_code == 422


def test_units_are_private_to_their_workspace(app):
    a, _ = signup(app)
    pid, tid = _project(a)
    uid = a.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]["floors"][0]["units"][0]["id"]
    b, _ = signup(app, email="other@acme.io", company_name="Other Realty")
    assert b.get(f"/api/v1/units/{uid}").status_code == 404
    assert b.get(f"/api/v1/projects/{pid}/towers/{tid}/building").status_code == 404
    assert b.post(f"/api/v1/units/{uid}/status", json={"status": "sold"}).status_code == 404
    assert b.get("/api/v1/units").get_json()["data"] == []


def test_duplicate_unit_numbers_and_add_floors(client):
    pid, tid = _project(client, floors=1, per_floor=2)
    assert client.post(f"/api/v1/projects/{pid}/towers", json={"name": "Tower D-13"}).status_code == 409
    r = client.post(f"/api/v1/projects/{pid}/towers/{tid}/floors", json={"count": 2, "units_per_floor": 3})
    assert r.get_json()["data"] == {"floors": 3, "units_created": 6}
    r = client.post("/api/v1/units", json={"tower_id": tid, "floor": 1, "number": "101"})
    assert r.status_code == 409
    r = client.post("/api/v1/units", json={"tower_id": tid, "floor": 1, "number": "199", "status": "self_occupied"})
    assert r.status_code == 201 and r.get_json()["data"]["status"] == "self_occupied"
