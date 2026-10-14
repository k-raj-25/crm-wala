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
