import io

from tests.conftest import signup


def test_import_flow_and_duplicates(app):
    cl, _ = signup(app)
    csv_text = "Name,Email Address,Mobile,Company,Title\nJohn Smith,john@example.com,+91 98765 43210,Acme Corp,CEO\nJane Doe,not-an-email,,Globex,CTO\nJohn Smith,john@example.com,9876543210,Acme Corp,CEO\n"
    r = cl.c.post("/api/v1/import/parse", data={"entity_type": "contacts", "file": (io.BytesIO(csv_text.encode()), "c.csv")}, headers=cl._h())
    assert r.status_code == 200, r.get_json()
    d = r.get_json()["data"]
    assert d["suggested_mapping"]["full_name"] == "Name" and d["suggested_mapping"]["email"] == "Email Address"
    body = {"entity_type": "contacts", "mapping": d["suggested_mapping"], "rows": d["rows"]}
    v = cl.post("/api/v1/import/validate", json=body).get_json()["data"]
    assert v["valid"] == 2 and any(e["field"] == "email" and e.get("severity") != "warning" for e in v["errors"])
    c = cl.post("/api/v1/import/commit", json={**body, "skip_duplicates": False}).get_json()["data"]
    assert c["created"] == 2 and c["skipped"] == 1
    groups = cl.get("/api/v1/duplicates?entity_type=contact").get_json()["data"]
    assert len(groups) == 1
    ids = [x["id"] for x in groups[0]["records"]]
    r = cl.post("/api/v1/duplicates/merge", json={"entity_type": "contact", "primary_id": ids[0], "merge_ids": ids[1:]})
    assert r.status_code == 200
    assert cl.get("/api/v1/duplicates?entity_type=contact").get_json()["data"] == []
    z = cl.get("/api/v1/export/workspace")
    assert z.data[:2] == b"PK"
