import io

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import Activity, Email, FileAsset, User
from app.models.base import utcnow
from tests.conftest import signup
from tests.test_realestate import _project


def _flats(cl, n=3):
    pid, tid = _project(cl)
    units = [u for f in cl.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]["floors"] for u in f["units"]][:n]
    cl.patch(f"/api/v1/units/{units[0]['id']}", json={"sale_price": 15000000, "area_sqft": 1500, "facing": "East"})
    cl.patch(f"/api/v1/units/{units[1]['id']}", json={"sale_price": 18000000, "area_sqft": 2000})
    return [u["id"] for u in units]


def test_preview_lines_flats_up_side_by_side_and_marks_the_best(client):
    ids = _flats(client)
    r = client.get(f"/api/v1/comparisons/preview?ids={','.join(ids)}")
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert [f["id"] for f in d["flats"]] == ids  # the order the user picked
    rows = {row["key"]: row for row in d["rows"]}
    assert rows["price"]["values"][0] == "₹1.5 Cr" and rows["price"]["best"] == [0]
    assert rows["area"]["best"] == [1]
    assert rows["rate"]["values"][1] == "₹9,000" and rows["rate"]["best"] == [1]
    assert rows["facing"]["values"] == ["East", "—", "—"]
    assert "rent" not in rows  # every flat blank, so the row is dropped
    assert rows["project"]["same"] is True


def test_preview_rejects_unknown_and_too_many_flats(client):
    ids = _flats(client)
    assert client.get("/api/v1/comparisons/preview?ids=00000000-0000-0000-0000-000000000000").status_code == 404
    other, _ = signup(client.app, email="b@other.io", company_name="Other")
    assert other.get(f"/api/v1/comparisons/preview?ids={ids[0]}").status_code == 404  # another workspace's flat
    assert client.get("/api/v1/comparisons/preview?ids=" + ",".join(ids * 3)).status_code == 200  # duplicates collapse
    assert client.get("/api/v1/comparisons/preview").status_code == 422


def test_pdf_download(client):
    ids = _flats(client)
    r = client.post("/api/v1/comparisons/pdf", json={"unit_ids": ids, "client_name": "Rohit Sharma"})
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")


def test_share_by_email_attaches_the_pdf(app, monkeypatch):
    cl, me = signup(app)
    ids = _flats(cl, 2)
    lead = cl.post("/api/v1/leads", json={"first_name": "Rohit", "email": "rohit@example.com", "phone": "98765 43210"}).get_json()["data"]
    body = {"unit_ids": ids, "channel": "email", "to": ["rohit@example.com"], "lead_id": lead["id"]}
    assert cl.post("/api/v1/comparisons/share", json=body).get_json()["error"]["code"] == "email_not_verified"
    with app.app_context(), bypass_scope():
        db.session.query(User).filter_by(email=me["user"]["email"]).update({"email_verified_at": utcnow()})
        db.session.commit()
    sent = {}
    from app.services.email import ConsoleProvider

    monkeypatch.setattr(ConsoleProvider, "send", lambda self, to, subject, html, **kw: sent.update(to=to, subject=subject, html=html, files=kw.get("attachments")))
    r = cl.post("/api/v1/comparisons/share", json=body)
    assert r.status_code == 200, r.get_json()
    assert sent["to"] == "rohit@example.com" and "Rohit" in sent["subject"]
    (name, mime, content), = sent["files"]
    assert name.endswith(".pdf") and mime == "application/pdf" and content.startswith(b"%PDF")
    with app.app_context(), bypass_scope():
        fa = db.session.get(FileAsset, r.get_json()["data"]["file_id"])
        assert str(fa.lead_id) == lead["id"]  # the PDF stays on the client's record
        assert db.session.query(Email).filter_by(lead_id=fa.lead_id).count() == 1


def test_share_on_whatsapp_gives_a_chat_link_and_a_public_pdf(client):
    ids = _flats(client, 2)
    contact = client.post("/api/v1/contacts", json={"first_name": "Meera", "phone": "+91 98765-43210"}).get_json()["data"]
    r = client.post("/api/v1/comparisons/share", json={"unit_ids": ids, "channel": "whatsapp", "contact_id": contact["id"], "phone": contact["phone"], "client_name": "Meera"})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert d["whatsapp_url"].startswith("https://wa.me/919876543210?text=Hi%20Meera")
    path = d["pdf_url"].split("/api/v1/", 1)[1]
    anon = client.app.test_client()  # no login: the client opens this from WhatsApp
    pdf = anon.get("/api/v1/" + path)
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    assert anon.get("/api/v1/" + path.replace(".pdf", "x.pdf")).status_code == 404  # wrong signature
    with client.app.app_context(), bypass_scope():
        assert db.session.query(Activity).filter_by(title="Flat comparison sent on WhatsApp").count() == 1


# ---- societies -------------------------------------------------------------------------------------------------------

def _societies(cl):
    """Two societies with sample photos, a brochure and floor plans; the second has cheaper 2 BHKs and fewer amenities."""
    from tests.test_realestate import _project

    a, _ = _project(cl)
    b = cl.post("/api/v1/projects", json={"name": "M3M Golf Estate", "city": "Gurgaon", "developer": "M3M"}).get_json()["data"]["id"]
    cl.post(f"/api/v1/projects/{b}/towers", json={"name": "A", "floors": 2, "units_per_floor": 2, "bhk": "2 BHK", "area_sqft": 1200, "sale_price": 9000000})
    assert cl.app.test_cli_runner().invoke(args=["seed-project-details"]).exit_code == 0
    cl.patch(f"/api/v1/projects/{a}", json={"amenities": ["Clubhouse", "Swimming pool", "Gym"]})
    cl.patch(f"/api/v1/projects/{b}", json={"amenities": ["Clubhouse", "Gym"]})
    media = {p: cl.get(f"/api/v1/projects/{p}/media").get_json()["data"] for p in (a, b)}
    return a, b, media


def test_society_preview_lines_up_layouts_and_amenities(client):
    a, b, _ = _societies(client)
    r = client.post("/api/v1/comparisons/societies/preview", json={"societies": [{"project_id": a}, {"project_id": b}]})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert [s["id"] for s in d["societies"]] == [a, b] and d["societies"][0]["chosen_sizes"] == ["3 BHK"]
    rows = {row["key"]: row for row in d["rows"]}
    assert rows["price"]["values"] == ["₹2 Cr", "₹90 L"] and rows["price"]["best"] == [1]
    assert rows["size:3bhk"]["values"][0].startswith("1,800 sq ft · from ₹2 Cr · 8 available · with floor plan") and rows["size:3bhk"]["values"][1] == "—"
    assert rows["size:2bhk"]["values"][0] == "—" and "6 available" in rows["size:2bhk"]["values"][1]
    assert rows["amenity:clubhouse"]["values"] == ["Yes", "Yes"] and rows["amenity:clubhouse"]["same"]
    assert rows["amenity:swimming pool"]["values"] == ["Yes", "No"]
    assert rows["amenity_count"]["best"] == [0]

    # only the layouts the broker kept are compared
    r = client.post("/api/v1/comparisons/societies/preview", json={"societies": [{"project_id": a, "sizes": []}, {"project_id": b}]})
    keys = {row["key"] for row in r.get_json()["data"]["rows"]}
    assert "size:3bhk" not in keys and "size:2bhk" in keys


def test_society_preview_rejects_unknown_and_too_many(client):
    a, _ = _project(client)
    assert client.post("/api/v1/comparisons/societies/preview", json={"societies": [{"project_id": "00000000-0000-0000-0000-000000000000"}]}).status_code == 404
    other, _ = signup(client.app, email="c@other.io", company_name="Other")
    assert other.post("/api/v1/comparisons/societies/preview", json={"societies": [{"project_id": a}]}).status_code == 404
    assert client.post("/api/v1/comparisons/societies/preview", json={"societies": [{"project_id": a}] * 5}).status_code == 422
    assert client.post("/api/v1/comparisons/societies/preview", json={"societies": []}).status_code == 422


def test_society_pdf_carries_the_chosen_photos_floor_plans_and_brochure(client):
    from pypdf import PdfReader

    a, b, media = _societies(client)
    bare = {"societies": [{"project_id": a, "sizes": []}, {"project_id": b, "sizes": []}]}
    r = client.post("/api/v1/comparisons/societies/pdf", json=bare)
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    base = len(PdfReader(io.BytesIO(r.data)).pages)
    assert "Society comparison" in r.headers["Content-Disposition"]

    brochure_pages = len(PdfReader(io.BytesIO(client.c.get(media[a]["brochures"][0]["url"]).data)).pages)
    full = {"societies": [{"project_id": a, "photo_ids": [p["id"] for p in media[a]["photos"][:3]], "brochure": True}, {"project_id": b, "sizes": []}]}
    r = client.post("/api/v1/comparisons/societies/pdf", json=full)
    assert r.status_code == 200, r.get_json()
    pages = PdfReader(io.BytesIO(r.data)).pages
    # + one page of photos for society A, its 3 BHK floor plan (a one-page PDF), and the whole brochure
    # after the table: one page of photos for society A, its 3 BHK floor plan (a one-page PDF), then the whole brochure
    section = pages[-(brochure_pages + 2)].extract_text()
    assert section.startswith("Ireo Victory Valley") and "RERA" in section
    assert "M3M Golf Estate" in pages[-(brochure_pages + 3)].extract_text()  # the last page of the table
    assert len(pages) - (brochure_pages + 2) >= base

    # a photo from the other society, or one deleted since, is skipped rather than failing the send
    stray = {"societies": [{"project_id": a, "sizes": [], "photo_ids": [media[b]["photos"][0]["id"]]}, {"project_id": b, "sizes": []}]}
    assert len(PdfReader(io.BytesIO(client.post("/api/v1/comparisons/societies/pdf", json=stray).data)).pages) == base


def test_society_pdf_survives_broken_files(client):
    from tests.test_realestate import _file

    a, _ = _project(client)
    photo = _file(client, "broken.jpg", "image/jpeg", project_id=a, doc_kind="photo").get_json()["data"]
    _file(client, "broken.pdf", "application/pdf", project_id=a, doc_kind="brochure")
    r = client.post("/api/v1/comparisons/societies/pdf", json={"societies": [{"project_id": a, "photo_ids": [photo["id"]], "brochure": True}]})
    assert r.status_code == 200 and r.data.startswith(b"%PDF")


def test_society_share_on_whatsapp(client):
    a, b, media = _societies(client)
    r = client.post("/api/v1/comparisons/societies/share", json={"societies": [{"project_id": a, "brochure": True}, {"project_id": b}], "channel": "whatsapp",
                                                                "phone": "98765 43210", "client_name": "Meera"})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert d["whatsapp_url"].startswith("https://wa.me/919876543210?text=Hi%20Meera") and "Ireo%20Victory%20Valley" in d["whatsapp_url"]
    pdf = client.app.test_client().get("/api/v1/" + d["pdf_url"].split("/api/v1/", 1)[1])
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    with client.app.app_context(), bypass_scope():
        assert db.session.query(Activity).filter_by(title="Society comparison sent on WhatsApp").count() == 1
