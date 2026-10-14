from app.services.privacy import mask
from tests.conftest import Client, signup
from tests.test_realestate import _project

PHONE = "+91 98765 43210"


def _member(app, owner, role: str, email: str) -> Client:
    roles = {r["key"]: r["id"] for r in owner.get("/api/v1/roles").get_json()["data"]}
    inv = owner.post("/api/v1/team/invitations", json={"email": email, "role_id": roles[role]}).get_json()["data"]
    m = Client(app)
    r = m.post("/api/v1/auth/invitations/accept", json={"token": inv["dev_token"], "name": email.split("@")[0].title(), "password": "Member#Pass123"})
    assert r.status_code == 200, r.get_json()
    return m


def test_mask_keeps_country_code_and_last_two_digits():
    assert mask(PHONE) == "+91 ••••• •••10"
    assert mask("9876543210") == "••••• •••10"
    assert mask("12") == "•••" and mask(None) is None and mask("") == ""


def test_sales_rep_sees_masked_numbers_everywhere(app):
    owner, _ = signup(app)
    lead = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "last_name": "Dhillon", "phone": PHONE, "intent": "buy", "bhk": "3 BHK",
                                              "budget_max": 22000000}).get_json()["data"]
    contact = owner.post("/api/v1/contacts", json={"first_name": "Ravi", "phone": PHONE}).get_json()["data"]
    assert lead["phone"] == PHONE and "phone_masked" not in lead
    rep = _member(app, owner, "sales_rep", "rep@acme.io")

    assert rep.get("/api/v1/auth/me").get_json()["data"]["workspace"]["hide_phones"] is True
    got = rep.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]
    assert got["phone"] == "+91 ••••• •••10" and got["phone_masked"] is True
    assert all("43210" not in (r["phone"] or "") for r in rep.get("/api/v1/leads").get_json()["data"])
    assert rep.get(f"/api/v1/contacts/{contact['id']}").get_json()["data"]["phone"] == "+91 ••••• •••10"
    conv = rep.get("/api/v1/whatsapp/conversation", query_string={"lead_id": lead["id"]}).get_json()["data"]
    assert conv["phone"] == "+91 ••••• •••10"
    assert owner.get("/api/v1/whatsapp/conversation", query_string={"lead_id": lead["id"]}).get_json()["data"]["phone"] == "+919876543210"

    csv = rep.get("/api/v1/leads/export").get_data(as_text=True)
    assert "Jasmine" in csv and "43210" not in csv
    assert "43210" in owner.get("/api/v1/leads/export").get_data(as_text=True)

    dup = rep.get("/api/v1/duplicates/check", query_string={"entity_type": "lead", "phone": "98765 43210"}).get_json()["data"]
    assert [d["name"] for d in dup] == ["Jasmine Dhillon"] and "43210" not in dup[0]["phone"]
    owner.post("/api/v1/leads", json={"first_name": "Jas", "phone": "9876543210"})
    groups = rep.get("/api/v1/duplicates", query_string={"entity_type": "lead"}).get_json()["data"]
    assert groups and all("43210" not in g["key"] and all("43210" not in (r["phone"] or "") for r in g["records"]) for g in groups)

    pid, tid = _project(owner)
    uid = owner.get(f"/api/v1/projects/{pid}/towers/{tid}/building").get_json()["data"]["floors"][0]["units"][0]["id"]
    owner.patch(f"/api/v1/units/{uid}", json={"status": "for_sale"})
    matches = rep.get(f"/api/v1/units/{uid}/matches").get_json()["data"]
    assert matches and all("43210" not in (m["phone"] or "") for m in matches)


def test_rep_edits_never_wipe_or_steal_a_hidden_number(app):
    owner, _ = signup(app)
    lead = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "phone": PHONE}).get_json()["data"]
    empty = owner.post("/api/v1/leads", json={"first_name": "No", "last_name": "Number"}).get_json()["data"]
    rep = _member(app, owner, "sales_rep", "rep@acme.io")

    # Saving the masked value (e.g. from "Edit all") or a blank keeps the real number.
    assert rep.patch(f"/api/v1/leads/{lead['id']}", json={"phone": "+91 ••••• •••10", "job_title": "Doctor"}).status_code == 200
    assert rep.patch(f"/api/v1/leads/{lead['id']}", json={"phone": None}).status_code == 200
    assert owner.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]["phone"] == PHONE
    # Overwriting a saved number is refused; adding a missing one is fine.
    r = rep.patch(f"/api/v1/leads/{lead['id']}", json={"phone": "+91 90000 00000"})
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "phone_hidden"
    assert rep.patch(f"/api/v1/leads/{empty['id']}", json={"phone": "+91 91111 22222"}).status_code == 200
    assert owner.get(f"/api/v1/leads/{empty['id']}").get_json()["data"]["phone"] == "+91 91111 22222"


def test_reveal_is_permissioned_and_logged(app):
    owner, _ = signup(app)
    lead = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "last_name": "Dhillon", "phone": PHONE}).get_json()["data"]
    rep = _member(app, owner, "sales_rep", "rep@acme.io")
    manager = _member(app, owner, "manager", "mgr@acme.io")

    r = rep.post(f"/api/v1/leads/{lead['id']}/reveal-phone", json={})
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "phone_hidden"
    assert manager.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]["phone_masked"] is True
    r = manager.post(f"/api/v1/leads/{lead['id']}/reveal-phone", json={})
    assert r.status_code == 200 and r.get_json()["data"]["phone"] == PHONE

    logs = owner.get("/api/v1/audit-logs", query_string={"action": "phone.revealed"}).get_json()["data"]
    assert len(logs) == 1 and logs[0]["actor_label"] == "Mgr" and logs[0]["summary"] == "Viewed the phone number of Jasmine Dhillon"
    assert logs[0]["after"] is None  # the number itself never lands in the log
    # The owner sees numbers anyway, so their reveals aren't logged.
    owner.post(f"/api/v1/leads/{lead['id']}/reveal-phone", json={})
    assert len(owner.get("/api/v1/audit-logs", query_string={"action": "phone.revealed"}).get_json()["data"]) == 1


def test_owner_controls_the_setting(app):
    owner, _ = signup(app)
    lead = owner.post("/api/v1/leads", json={"first_name": "Jasmine", "phone": PHONE}).get_json()["data"]
    admin = _member(app, owner, "admin", "admin@acme.io")
    rep = _member(app, owner, "sales_rep", "rep@acme.io")
    assert admin.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]["phone"] == PHONE  # admins have "See phone numbers"
    assert admin.patch("/api/v1/workspace", json={"hide_phones": False}).status_code == 403

    assert owner.patch("/api/v1/workspace", json={"hide_phones": False}).get_json()["data"]["hide_phones"] is False
    assert rep.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]["phone"] == PHONE
    owner.patch("/api/v1/workspace", json={"hide_phones": True})
    assert rep.get(f"/api/v1/leads/{lead['id']}").get_json()["data"]["phone_masked"] is True


def test_ai_payloads_are_scrubbed():
    from app.services.privacy import _scrub

    out = _scrub({"leads": [{"name": "Jasmine", "phone": PHONE, "whatsapp": "https://wa.me/919876543210?text=hi", "budget_max": 25000000}],
                  "message": "Several leads match: Jasmine (+91 98765 43210, id 7). Budget 25000000."})
    assert out["leads"][0] == {"name": "Jasmine", "phone": "+91 ••••• •••10", "whatsapp": None, "budget_max": 25000000}
    assert "43210" not in out["message"] and "25000000" in out["message"]
