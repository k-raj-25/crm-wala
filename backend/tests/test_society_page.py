from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import Activity, Notification
from tests.conftest import signup
from tests.test_comparisons import _societies


def _token(url: str) -> str:
    return url.rsplit("/s/", 1)[1]


def test_public_page_shows_the_society_without_login(client):
    a, b, media = _societies(client)
    r = client.post(f"/api/v1/projects/{a}/share", json={"channel": "link"})
    assert r.status_code == 200, r.get_json()
    url = r.get_json()["data"]["url"]
    assert "/s/" in url and len(_token(url)) < 70

    anon = client.app.test_client()  # the client opens it from WhatsApp, not logged in
    r = anon.get(f"/api/v1/public/societies/{_token(url)}")
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    s = d["society"]
    assert s["name"] == "Ireo Victory Valley" and s["location"] == "Sector 67, Gurgaon" and s["starting_price"] == "₹2 Cr"
    assert s["available"] == 8 and s["towers"] == 1 and "Swimming pool" in s["amenities"]
    assert len(d["photos"]) == len(media[a]["photos"]) and d["brochure"]["filename"]
    three = next(z for z in d["sizes"] if z["label"] == "3 BHK")
    assert three["available"] == 8 and three["from_price"] == "₹2 Cr" and three["floor_plan"]["download_url"].endswith("?download=1")
    assert d["contact"]["name"] and d["company"]["name"]
    assert "owner_id" not in s and "tags" not in s

    # its files open without login, and download as attachments
    plan = anon.get("/api/v1/" + three["floor_plan"]["download_url"].split("/api/v1/", 1)[1])
    assert plan.status_code == 200 and "attachment" in plan.headers["Content-Disposition"]
    photo = anon.get("/api/v1/" + d["photos"][0]["url"].split("/api/v1/", 1)[1])
    assert photo.status_code == 200 and "attachment" not in photo.headers.get("Content-Disposition", "")
    # but only this society's photos, floor plans and brochure
    other = media[b]["photos"][0]["id"]
    assert anon.get(f"/api/v1/public/societies/{_token(url)}/files/{other}").status_code == 404


def test_tampered_or_dead_links_are_404(client):
    a, _, _ = _societies(client)
    token = _token(client.post(f"/api/v1/projects/{a}/share", json={"channel": "link"}).get_json()["data"]["url"])
    anon = client.app.test_client()
    bad = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    assert anon.get(f"/api/v1/public/societies/{bad}").status_code == 404
    assert anon.get("/api/v1/public/societies/nonsense").status_code == 404
    client.delete(f"/api/v1/projects/{a}")
    assert anon.get(f"/api/v1/public/societies/{token}").status_code == 404


def test_another_workspace_cannot_share_my_society(client):
    a, _, _ = _societies(client)
    other, _ = signup(client.app, email="z@other.io", company_name="Other")
    assert other.post(f"/api/v1/projects/{a}/share", json={"channel": "link"}).status_code == 404


def test_hide_prices(client):
    a, _, _ = _societies(client)
    token = _token(client.post(f"/api/v1/projects/{a}/share", json={"channel": "link", "hide_prices": True}).get_json()["data"]["url"])
    d = client.app.test_client().get(f"/api/v1/public/societies/{token}").get_json()["data"]
    assert d["society"]["starting_price"] is None and d["society"]["price_range"] is None and all(z["from_price"] is None for z in d["sizes"])


def test_whatsapp_share_files_on_the_lead_and_opening_tells_the_employee(client):
    a, _, _ = _societies(client)
    lead = client.post("/api/v1/leads", json={"first_name": "Meera", "last_name": "Iyer", "phone": "98765 43210"}).get_json()["data"]
    r = client.post(f"/api/v1/projects/{a}/share", json={"channel": "whatsapp", "lead_id": lead["id"], "phone": "98765 43210"})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert d["whatsapp_url"].startswith("https://wa.me/919876543210?text=Hi%20Meera") and d["url"] in d["text"]
    token = _token(d["url"])

    anon = client.app.test_client()
    assert anon.get(f"/api/v1/public/societies/{token}").get_json()["data"]["shared_with"] == "Meera"
    assert anon.post(f"/api/v1/public/societies/{token}/opened").get_json()["data"]["noted"] is True
    assert anon.post(f"/api/v1/public/societies/{token}/opened").get_json()["data"]["noted"] is False  # not again within a few hours
    with client.app.app_context(), bypass_scope():
        assert db.session.query(Activity).filter_by(title="Ireo Victory Valley society page sent on WhatsApp").count() == 1
        assert db.session.query(Activity).filter_by(title="Meera Iyer opened the Ireo Victory Valley society page").count() == 1
        assert db.session.query(Notification).filter_by(type="client_viewing").count() == 1

    # a plain link with no lead never notes anything
    plain = _token(client.post(f"/api/v1/projects/{a}/share", json={"channel": "link"}).get_json()["data"]["url"])
    assert anon.post(f"/api/v1/public/societies/{plain}/opened").get_json()["data"]["noted"] is False


def test_email_share_needs_an_address(client):
    a, _, _ = _societies(client)
    r = client.post(f"/api/v1/projects/{a}/share", json={"channel": "email"})
    assert r.status_code in (403, 422)
