import datetime as dt

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import AuditLog, PriceChange, Unit, UnitEvent
from app.models.base import utcnow
from tests.conftest import signup
from tests.test_phone_privacy import _member
from tests.test_realestate import _project


def _flats(cl, pid, tid) -> dict:
    b = cl.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]
    return {u["number"]: u for f in b["floors"] for u in f["units"]}


def _status(cl, uid, status):
    r = cl.post(f"/api/v1/units/{uid}/status", json={"status": status})
    assert r.status_code == 200, r.get_json()


def _hot_tower(cl):
    """Floors 1-3: four flats booked, the last two held and released three times each. Ground floor: two fresh flats."""
    pid, tid = _project(cl)
    f = _flats(cl, pid, tid)
    for n in ("101", "102", "201", "202"):
        _status(cl, f[n]["id"], "booked")
    for n in ("301", "302"):
        for _ in range(3):
            _status(cl, f[n]["id"], "on_hold")
            _status(cl, f[n]["id"], "for_sale")
    return pid, tid, f


def test_busy_flats_get_a_raise_and_the_owner_applies_it(client):
    pid, tid, f = _hot_tower(client)
    d = client.get(f"/api/v1/pricing/projects/{pid}/suggestions").get_json()["data"]
    assert d["can_apply"] is True
    [s] = d["suggestions"]
    assert s["rule"] == "raise_hot" and s["pct"] == 3
    assert s["headline"] == "3BHKs on floors 1 to 3, Tower D-13 had 6 holds and 4 booked in 60 days and only 2 are left. Raise the price by 3%."
    assert [u["number"] for u in s["units"]] == ["301", "302"] and s["evidence"]["taken"] == 4

    # nothing has changed yet: suggestions only suggest
    assert _flats(client, pid, tid)["301"]["sale_price"] == 20000000

    r = client.post(f"/api/v1/pricing/projects/{pid}/apply", json={"segment_key": s["segment_key"], "rule": s["rule"], "pct": 3, "headline": s["headline"]})
    assert r.status_code == 200, r.get_json()
    flats = _flats(client, pid, tid)
    assert flats["301"]["sale_price"] == 20600000 and flats["302"]["sale_price"] == 20600000
    assert flats["101"]["sale_price"] == 20000000  # booked flats keep the price their buyer agreed
    hist = client.get(f"/api/v1/units/{f['301']['id']}/history").get_json()["data"]
    assert hist[0]["type"] == "price" and "₹2 Cr → ₹2.06 Cr (+3%)" in hist[0]["note"]
    with client.app.app_context(), bypass_scope():
        row = db.session.query(AuditLog).filter_by(action="pricing.applied").one()
        assert "+3%" in row.summary and row.before == {"301": 20000000.0, "302": 20000000.0} and row.after["301"] == 20600000.0

    # the group is left alone while the change shows its effect, and can't be repriced again straight away
    assert client.get(f"/api/v1/pricing/projects/{pid}/suggestions").get_json()["data"]["suggestions"] == []
    again = client.post(f"/api/v1/pricing/projects/{pid}/apply", json={"segment_key": s["segment_key"], "rule": s["rule"], "pct": 3})
    assert again.status_code == 409

    [c] = client.get(f"/api/v1/pricing/projects/{pid}/changes").get_json()["data"]
    assert c["status"] == "applied" and c["pct"] == 3 and c["decided_by_name"] == "Asha Rao" and c["tracking"]["verdict"] == "too_early"

    # undo puts the old price back, except on a flat someone has repriced by hand since
    assert client.patch(f"/api/v1/units/{f['302']['id']}", json={"sale_price": 21000000}).status_code == 200
    u = client.post(f"/api/v1/pricing/changes/{c['id']}/undo").get_json()["data"]
    assert u == {"restored": ["301"], "skipped": ["302"]}
    flats = _flats(client, pid, tid)
    assert flats["301"]["sale_price"] == 20000000 and flats["302"]["sale_price"] == 21000000
    assert client.post(f"/api/v1/pricing/changes/{c['id']}/undo").status_code == 409


def test_flats_nobody_wants_get_a_cut_and_can_be_dismissed(client):
    pid, tid = _project(client)
    f = _flats(client, pid, tid)
    for n in ("001", "002"):
        _status(client, f[n]["id"], "for_sale")
    with client.app.app_context(), bypass_scope():  # listed three months ago, no interest since
        db.session.query(Unit).filter(Unit.project_id == pid).update({"status_changed_at": utcnow() - dt.timedelta(days=90)})
        db.session.query(UnitEvent).update({"created_at": utcnow() - dt.timedelta(days=90)})
        db.session.commit()
    sugg = client.get(f"/api/v1/pricing/projects/{pid}/suggestions").get_json()["data"]["suggestions"]
    cut = next(s for s in sugg if "ground floor" in s["segment_label"])
    assert cut["rule"] == "cut_cold" and cut["pct"] == -2
    assert cut["headline"] == "3BHKs on the ground floor, Tower D-13: no holds, visits or enquiries in 60 days. Cut the price by 2%."

    # a buyer who fits but never asked is mentioned
    client.post("/api/v1/leads", json={"first_name": "Ravi", "intent": "buy", "bhk": "3 BHK", "budget_max": 21000000})
    cut = next(s for s in client.get(f"/api/v1/pricing/projects/{pid}/suggestions").get_json()["data"]["suggestions"] if s["rule"] == "cut_cold" and "ground" in s["segment_label"])
    assert "1 buyer in your leads fits them but none asked." in cut["headline"]

    r = client.post(f"/api/v1/pricing/projects/{pid}/dismiss", json={"segment_key": cut["segment_key"], "rule": cut["rule"]})
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "dismissed"
    left = client.get(f"/api/v1/pricing/projects/{pid}/suggestions").get_json()["data"]["suggestions"]
    assert all(s["segment_key"] != cut["segment_key"] for s in left)
    assert _flats(client, pid, tid)["001"]["sale_price"] == 20000000


def test_demand_colours_follow_holds_visits_and_comparisons(client):
    pid, tid, f = _hot_tower(client)
    assert client.post("/api/v1/comparisons/pdf", json={"unit_ids": [f["001"]["id"]], "client_name": "Ravi"}).status_code == 200
    d = client.get(f"/api/v1/pricing/projects/{pid}/demand", query_string={"tower_id": tid}).get_json()["data"]["units"]
    assert d[f["301"]["id"]]["level"] == "hot" and d[f["301"]["id"]]["holds"] == 3
    assert d[f["001"]["id"]]["compared"] == 1 and d[f["001"]["id"]]["level"] == "cool"
    assert d[f["002"]["id"]]["level"] == "cold"
    assert f["101"]["id"] not in d  # booked flats aren't coloured by demand
    assert "Comparison PDF downloaded for Ravi" in client.get(f"/api/v1/units/{f['001']['id']}/history").get_json()["data"][0]["note"]


def test_tracking_compares_the_same_days_before_and_after(client):
    pid, tid, f = _hot_tower(client)
    s = client.get(f"/api/v1/pricing/projects/{pid}/suggestions").get_json()["data"]["suggestions"][0]
    pc = client.post(f"/api/v1/pricing/projects/{pid}/apply", json={"segment_key": s["segment_key"], "rule": s["rule"], "pct": 3}).get_json()["data"]
    with client.app.app_context(), bypass_scope():
        # the change was 10 days ago: six holds but no booking in the 10 days before it, one booking after it
        now = utcnow()
        db.session.query(PriceChange).filter_by(id=pc["id"]).update({"created_at": now - dt.timedelta(days=10)})
        db.session.query(UnitEvent).filter(UnitEvent.to_status == "on_hold").update({"created_at": now - dt.timedelta(days=15)})
        db.session.commit()
    _status(client, f["301"]["id"], "booked")
    [c] = client.get(f"/api/v1/pricing/projects/{pid}/changes").get_json()["data"]
    t = c["tracking"]
    assert t["days"] == 10 and t["before"] == {"holds": 6, "booked": 0} and t["after"] == {"holds": 0, "booked": 1} and t["verdict"] == "faster"


def test_only_owners_and_admins_change_prices(app):
    owner, _ = signup(app)
    manager = _member(app, owner, "manager", "meena@acme.io")
    rep = _member(app, owner, "sales_rep", "rahul@acme.io")
    pid, tid, f = _hot_tower(owner)
    s = manager.get(f"/api/v1/pricing/projects/{pid}/suggestions").get_json()["data"]
    assert s["can_apply"] is False and len(s["suggestions"]) == 1
    body = {"segment_key": s["suggestions"][0]["segment_key"], "rule": "raise_hot", "pct": 3}
    assert manager.post(f"/api/v1/pricing/projects/{pid}/apply", json=body).status_code == 403
    assert rep.get(f"/api/v1/pricing/projects/{pid}/suggestions").status_code == 403
    assert owner.post(f"/api/v1/pricing/projects/{pid}/apply", json={**body, "pct": 25}).status_code == 422
    other, _ = signup(app, email="b@other.io", company_name="Other")
    assert other.get(f"/api/v1/pricing/projects/{pid}/suggestions").status_code == 404
