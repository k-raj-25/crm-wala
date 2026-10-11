import decimal

from app.core.tenant import bypass_scope
from app.extensions import db
from app.models import Workspace
from app.services.portal_leads import parse_amount, parse_email

# Representative of the 99acres "response on your property" mail after an inbound-parse provider flattens it to text.
SAMPLE_SUBJECT = "You have received a response on your property: 3 BHK Apartment for Sale in Ireo Victory Valley, Sector 67, Gurgaon"
SAMPLE_TEXT = """Dear Sunrise Realty,

A user has shown interest in your property listed on 99acres.com (ID: A73912458)

Details of the user:
Name: Rahul Sharma
Email: rahul.sharma@example.com
Mobile: +91-9876543210
City: Gurgaon
Budget: 1.8 Cr - 2.2 Cr

Message: Hi, I am interested in your 3 BHK in Ireo Victory Valley. Please call me after 6 pm.

Regards,
Team 99acres
"""


def _token(cl):
    return cl.get("/api/v1/integrations").get_json()["data"]["lead_form"]["token"]


def _lead(cl, lid):
    return cl.get(f"/api/v1/leads/{lid}").get_json()["data"]


def test_parse_sample_email():
    e = parse_email(SAMPLE_SUBJECT, SAMPLE_TEXT)
    assert (e.name, e.email, e.phone, e.location) == ("Rahul Sharma", "rahul.sharma@example.com", "+91-9876543210", "Gurgaon")
    assert e.property.startswith("3 BHK Apartment for Sale in Ireo Victory Valley") and e.property_id == "A73912458"
    assert e.message.startswith("Hi, I am interested")
    # HTML tables flatten to "Label\nvalue"
    t = parse_email("New enquiry on 99acres", "Name\nPriya Verma\nMobile Number\n9812345678\nQuery\nIs it still available?")
    assert (t.name, t.phone, t.message) == ("Priya Verma", "9812345678", "Is it still available?")


def test_parse_amount():
    D = decimal.Decimal
    assert parse_amount("₹ 1.25 Cr") == (None, D(12500000))
    assert parse_amount("50 Lac - 1 Cr") == (D(5000000), D(10000000))
    assert parse_amount("85,00,000") == (None, D(8500000))
    assert parse_amount(None) == (None, None)


def test_99acres_email_creates_lead_awaiting_review(client):
    pid = client.post("/api/v1/projects", json={"name": "Ireo Victory Valley", "city": "Gurgaon"}).get_json()["data"]["id"]
    tok = _token(client)
    mail = {"from": "noreply@99acres.com", "to": ["leads@sunrise.in"], "subject": SAMPLE_SUBJECT, "text": SAMPLE_TEXT, "message_id": "<abc123@99acres.com>"}
    # the existing inbound e-mail webhook recognises 99acres mail and routes it to intake
    r = client.post(f"/api/v1/inbound/email/{tok}", json=mail)
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert d["created"] is True and d["status"] == "pending_review"

    lead = _lead(client, d["lead_id"])
    assert (lead["first_name"], lead["last_name"], lead["email"], lead["phone"]) == ("Rahul", "Sharma", "rahul.sharma@example.com", "+919876543210")
    assert lead["source"] == "99acres" and lead["status"] == "pending_review" and lead["owner_id"] is None and "99acres" in lead["tags"]
    assert (lead["bhk"], lead["property_type"], lead["intent"], lead["location"]) == ("3 BHK", "apartment", "buy", "Gurgaon")
    assert decimal.Decimal(str(lead["budget_min"])) == 18000000 and decimal.Decimal(str(lead["budget_max"])) == 22000000
    assert lead["project_id"] == pid  # the listing names a project in this workspace
    assert lead["custom"]["portal_property_id"] == "A73912458"

    # it shows in the review queue and the status exists in the workspace settings
    assert [x["id"] for x in client.get("/api/v1/leads?status=pending_review").get_json()["data"]] == [d["lead_id"]]
    # the same mail delivered twice does not make a second lead
    again = client.post(f"/api/v1/inbound/email/{tok}", json=mail).get_json()["data"]
    assert again == {**d, "created": False}

    # the owner accepts it: it becomes a normal new enquiry
    r = client.patch(f"/api/v1/leads/{d['lead_id']}", json={"status": "new"})
    assert r.status_code == 200 and r.get_json()["data"]["status"] == "new"


def test_99acres_lead_push(client):
    tok = _token(client)
    batch = {"leads": [
        {"QueryId": "Q-1001", "SenderName": "Anita Desai", "SenderMobile": "9811122233", "SenderEmail": "anita@example.com",
         "Message": "Looking for 2 BHK on rent", "Property": {"Name": "2 BHK Builder Floor, DLF Phase 3", "Id": "R555"}, "City": "Gurgaon"},
        {"QueryId": "Q-1002", "SenderName": "No Contact"},  # nobody to call: rejected, nothing created
    ]}
    r = client.post(f"/api/v1/inbound/99acres/{tok}", json=batch)
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert d["received"] == 2 and d["created"] == 1 and d["results"][1]["lead_id"] is None
    lead = _lead(client, d["results"][0]["lead_id"])
    assert lead["status"] == "pending_review" and lead["first_name"] == "Anita" and lead["phone"] == "9811122233"
    assert (lead["intent"], lead["bhk"], lead["custom"]["portal_enquiry_id"], lead["custom"]["portal_property_id"]) == ("rent", "2 BHK", "Q-1001", "R555")
    # re-pushing the same enquiry id is idempotent
    assert client.post(f"/api/v1/inbound/99acres/{tok}", json=batch["leads"][0]).get_json()["data"]["created"] == 0
    assert client.post("/api/v1/inbound/99acres/not-a-token", json=batch).status_code == 404
    assert client.post(f"/api/v1/inbound/99acres/{tok}", json=[]).status_code == 422


def test_pending_status_added_to_older_workspaces(client):
    with client.app.app_context(), bypass_scope():
        ws = db.session.query(Workspace).one()
        ws.settings = {**ws.settings, "lead_statuses": [s for s in ws.settings["lead_statuses"] if s["key"] != "pending_review"]}
        db.session.commit()
    tok = _token(client)
    r = client.post(f"/api/v1/inbound/99acres/{tok}", json={"name": "Old Workspace", "mobile": "9800000000", "enquiry_id": "X1"})
    assert r.get_json()["data"]["created"] == 1
    keys = [s["key"] for s in client.get("/api/v1/workspace").get_json()["data"]["lead_statuses"]]
    assert keys[:2] == ["new", "pending_review"]
