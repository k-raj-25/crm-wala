"""WhatsApp Business via the Meta WhatsApp Cloud API.

Each workspace connects its own WhatsApp Business number (phone number ID, WhatsApp Business Account ID, a permanent access
token and the Meta app secret); nothing is shared across organisations. Connecting verifies the details with Meta and
subscribes the Meta app to the WhatsApp Business Account so replies are delivered to our webhook.

Outbound: approved templates (any time) and documents / images such as brochures and floor plans. Meta only allows
free-form messages inside the 24-hour customer-service window that opens when the client last wrote to you; outside it
a document can still go out as the header of an approved "media template" chosen in WhatsApp settings. Files are
uploaded to Meta's media store first, so storage never has to be publicly reachable.
Inbound: Meta calls /api/v1/inbound/whatsapp/<webhook_token>; replies land on the matching lead/contact timeline and
delivery receipts update message status.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import re
import secrets
from typing import Any

import httpx
from flask import current_app, g, has_request_context

from app.core.errors import ApiError
from app.extensions import db
from app.models import Contact, FileAsset, Integration, Lead, Project, Unit, WhatsAppMessage
from app.models.base import utcnow
from app.services import activities, integrations, storage

log = logging.getLogger("app.whatsapp")

GRAPH = "https://graph.facebook.com"
WINDOW = dt.timedelta(hours=24)
STATUS_RANK = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}
DOC_KINDS = {"brochure": "Brochure", "floor_plan": "Floor plan", "price_list": "Price list", "photo": "Photo", "other": "Document"}
IMAGE_MAX_BYTES = 5 * 1024 * 1024  # Meta limits; documents may be up to 100 MB
DOC_MAX_BYTES = 100 * 1024 * 1024


# ---- connection --------------------------------------------------------------------------------------------------

def _url(path: str) -> str:
    return f"{GRAPH}/{current_app.config['WHATSAPP_GRAPH_VERSION']}/{path}"


def connection(workspace_id) -> Integration:
    i = integrations.get(workspace_id, "whatsapp")
    if i is None or i.status not in ("connected", "error") or not i.credentials_enc:
        raise ApiError(409, "whatsapp_not_connected", "Connect WhatsApp in Integrations first.")
    return i


def _get(path: str, token: str, **params) -> httpx.Response:
    try:
        return httpx.get(_url(path), params=params or None, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    except httpx.HTTPError:
        raise ApiError(502, "whatsapp_unreachable", "Couldn't reach WhatsApp. Please try again in a minute.")


def verify_and_subscribe(creds: dict) -> dict:
    """Check every detail against Meta before storing it, then subscribe the app to the WhatsApp Business Account so
    Meta starts delivering replies and delivery receipts. Returns the number's display phone and verified name."""
    tok = creds["access_token"]
    r = _get(creds["phone_number_id"], tok, fields="display_phone_number,verified_name")
    if r.status_code >= 400:
        raise ApiError(422, "validation_error", "Meta rejected the phone number ID or access token.", {"phone_number_id": _meta_error(r)})
    info = r.json()
    r = _get(f"{creds['waba_id']}/message_templates", tok, limit=1, fields="name")
    if r.status_code >= 400:
        raise ApiError(422, "validation_error", "Meta rejected the WhatsApp Business Account ID, or the token can't manage its templates "
                       "(it needs the whatsapp_business_management permission).", {"waba_id": _meta_error(r)})
    try:
        r = httpx.post(_url(f"{creds['waba_id']}/subscribed_apps"), headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    except httpx.HTTPError:
        raise ApiError(502, "whatsapp_unreachable", "Couldn't reach WhatsApp. Please try again in a minute.")
    if r.status_code >= 400:
        raise ApiError(422, "validation_error", "Meta wouldn't subscribe your app to this WhatsApp account, so replies wouldn't arrive.",
                       {"waba_id": _meta_error(r)})
    return info


def new_webhook_config() -> dict:
    return {"webhook_token": secrets.token_urlsafe(24), "verify_token": secrets.token_urlsafe(18)}


def _meta_error(r: httpx.Response) -> str:
    try:
        e = r.json().get("error", {})
        return (e.get("error_data", {}) or {}).get("details") or e.get("message") or r.text[:200]
    except ValueError:
        return r.text[:200]


# ---- phone numbers -----------------------------------------------------------------------------------------------

def normalize_phone(raw: str | None, default_cc: str | None = None) -> str | None:
    """'+91 98765-43210', '098765 43210' and '9876543210' all become '919876543210' (E.164 digits, no '+')."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if raw.strip().startswith("00"):
        digits = digits[2:]
    cc = default_cc or current_app.config["WHATSAPP_DEFAULT_COUNTRY_CODE"]
    if len(digits) == 11 and digits.startswith("0"):
        digits = cc + digits[1:]
    elif len(digits) == 10 and not raw.strip().startswith("+"):
        digits = cc + digits
    return digits if 8 <= len(digits) <= 15 else None


def _same_number_clause(col, phone: str):
    """Stored CRM phones are free text; compare on the last 10 digits so formatting differences don't matter."""
    from sqlalchemy import func

    return func.right(func.regexp_replace(func.coalesce(col, ""), r"\D", "", "g"), 10) == phone[-10:]


def find_record(workspace_id, phone: str) -> tuple[str, Any] | None:
    c = db.session.query(Contact).filter(Contact.workspace_id == workspace_id, Contact.deleted_at.is_(None), _same_number_clause(Contact.phone, phone)) \
        .order_by(Contact.last_activity_at.desc().nullslast()).first()
    if c:
        return "contact", c
    lead = db.session.query(Lead).filter(Lead.workspace_id == workspace_id, Lead.deleted_at.is_(None), Lead.converted_at.is_(None), _same_number_clause(Lead.phone, phone)) \
        .order_by(Lead.last_activity_at.desc().nullslast()).first()
    return ("lead", lead) if lead else None


def window_open(workspace_id, phone: str) -> bool:
    last = db.session.query(WhatsAppMessage.created_at).filter(WhatsAppMessage.workspace_id == workspace_id, WhatsAppMessage.phone == phone,
                                                               WhatsAppMessage.direction == "inbound").order_by(WhatsAppMessage.created_at.desc()).first()
    return bool(last) and last[0] > utcnow() - WINDOW


# ---- templates ---------------------------------------------------------------------------------------------------

def _vars(text: str) -> list[str]:
    """Placeholder names in order of first appearance: ['1', '2'] for positional templates, ['first_name', ...] for named ones."""
    out: list[str] = []
    for v in re.findall(r"\{\{\s*(\w+)\s*\}\}", text or ""):
        if v not in out:
            out.append(v)
    return out


def _shape_template(t: dict) -> dict:
    comps = t.get("components", [])
    body = next((c.get("text", "") for c in comps if c.get("type") == "BODY"), "")
    header = next((c for c in comps if c.get("type") == "HEADER"), None)
    fmt = header.get("format") if header else None
    buttons = [b for c in comps if c.get("type") == "BUTTONS" for b in c.get("buttons", [])]
    # We fill body placeholders and a document/image header. Templates that also need header text or button values are listed but not sendable.
    supported = fmt in (None, "TEXT", "DOCUMENT", "IMAGE") and not (fmt == "TEXT" and _vars(header.get("text", ""))) \
        and not any(_vars(b.get("url", "")) for b in buttons)
    names = _vars(body)
    return {"name": t["name"], "language": t.get("language"), "category": t.get("category"), "body": body, "body_params": len(names),
            "param_names": names, "header": fmt, "supported": supported}


def list_templates(i: Integration) -> list[dict]:
    creds = integrations.get_creds(i)
    out: list[dict] = []
    url, params = _url(f"{creds['waba_id']}/message_templates"), {"status": "APPROVED", "limit": 100, "fields": "name,language,status,category,components"}
    for _ in range(5):  # a few pages is plenty for a brokerage
        try:
            r = httpx.get(url, params=params, headers={"Authorization": f"Bearer {creds['access_token']}"}, timeout=15)
        except httpx.HTTPError:
            raise ApiError(502, "whatsapp_unreachable", "Couldn't reach WhatsApp. Please try again in a minute.")
        if r.status_code >= 400:
            _raise_for(i, r)
        j = r.json()
        out += [_shape_template(t) for t in j.get("data", []) if t.get("status", "APPROVED") == "APPROVED"]
        url, params = (j.get("paging") or {}).get("next"), None
        if not url:
            break
    return out


# ---- sending -----------------------------------------------------------------------------------------------------

def _raise_for(i: Integration, r: httpx.Response) -> None:
    try:
        err = r.json().get("error", {})
    except ValueError:
        err = {}
    code, detail = err.get("code"), _meta_error(r)
    if code == 190 or r.status_code == 401:
        i.status, i.last_error = "reconnect", "WhatsApp access token expired or was revoked. Reconnect to keep messaging."
        db.session.commit()  # keep the state change even though the request fails
        raise ApiError(409, "whatsapp_reconnect", i.last_error)
    if code in (131047, 131026) or "re-engagement" in detail.lower():
        raise ApiError(409, "whatsapp_window_closed", "This client hasn't messaged you in the last 24 hours, so WhatsApp only allows an approved template.")
    if code == 132001:
        raise ApiError(422, "whatsapp_template_missing", "That template isn't approved for this number or language.")
    raise ApiError(502, "whatsapp_failed", f"WhatsApp didn't accept the message: {detail}")


def _post(i: Integration, payload: dict) -> str:
    creds = integrations.get_creds(i)
    try:
        r = httpx.post(_url(f"{creds['phone_number_id']}/messages"), json={"messaging_product": "whatsapp", "recipient_type": "individual", **payload},
                       headers={"Authorization": f"Bearer {creds['access_token']}"}, timeout=20)
    except httpx.HTTPError:
        raise ApiError(502, "whatsapp_unreachable", "Couldn't reach WhatsApp. Please try again in a minute.")
    if r.status_code >= 400:
        _raise_for(i, r)
    i.last_synced_at = utcnow()
    return r.json()["messages"][0]["id"]


def _media(i: Integration, file: FileAsset) -> tuple[str, dict]:
    """Upload the file to Meta's media store and return the message part that references it."""
    is_image = file.mime_type in ("image/jpeg", "image/png")
    if file.size_bytes > (IMAGE_MAX_BYTES if is_image else DOC_MAX_BYTES):
        raise ApiError(413, "file_too_large", f"WhatsApp accepts {'images up to 5 MB' if is_image else 'documents up to 100 MB'}.")
    creds = integrations.get_creds(i)
    content = storage.get_storage().read(file.storage_key)
    try:
        r = httpx.post(_url(f"{creds['phone_number_id']}/media"), headers={"Authorization": f"Bearer {creds['access_token']}"}, timeout=60,
                       data={"messaging_product": "whatsapp", "type": file.mime_type}, files={"file": (file.filename, content, file.mime_type)})
    except httpx.HTTPError:
        raise ApiError(502, "whatsapp_unreachable", "Couldn't reach WhatsApp. Please try again in a minute.")
    if r.status_code >= 400:
        _raise_for(i, r)
    media_id = r.json()["id"]
    return ("image", {"id": media_id}) if is_image else ("document", {"id": media_id, "filename": file.filename})


def _render(body: str, names: list[str], params: list[str]) -> str:
    values = dict(zip(names, params))
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: values.get(m.group(1), m.group(0)), body)


def _body_parameters(names: list[str], params: list[str]) -> list[dict]:
    if all(n.isdigit() for n in names):
        return [{"type": "text", "text": p} for p in params]
    return [{"type": "text", "parameter_name": n, "text": p} for n, p in zip(names, params)]


def recipient_phone(entity) -> str:
    phone = normalize_phone(entity.phone)
    if not phone:
        raise ApiError(422, "validation_error", f"{entity.name} doesn't have a valid mobile number.", {"phone": "Add a mobile number first"})
    return phone


def send(i: Integration, entity_type: str, entity, *, text: str | None = None, template: dict | None = None,
         file: FileAsset | None = None, caption: str | None = None, unit: Unit | None = None) -> WhatsAppMessage:
    """Send one message to a lead or contact and log it on their timeline. Exactly one of text / template / file."""
    ws_id = entity.workspace_id
    phone = recipient_phone(entity)
    data: dict = {}
    if template:
        params = [str(p)[:1000] for p in template.get("params") or []]
        names = template.get("param_names") or [str(n + 1) for n in range(len(params))]
        comps: list[dict] = []
        if file is not None:
            kind_, media = _media(i, file)
            comps.append({"type": "header", "parameters": [{"type": kind_, kind_: media}]})
        if params:
            comps.append({"type": "body", "parameters": _body_parameters(names, params)})
        payload = {"to": phone, "type": "template", "template": {"name": template["name"], "language": {"code": template["language"]}, **({"components": comps} if comps else {})}}
        kind, body = "template", _render(template.get("body") or "", names, params) or None
        data["params"] = params
    elif file is not None:
        if not window_open(ws_id, phone):
            mt = (i.config or {}).get("media_template")
            if not mt:
                raise ApiError(409, "whatsapp_window_closed",
                               f"{entity.name} hasn't messaged you in the last 24 hours, so WhatsApp only allows approved templates. "
                               "Choose a brochure template in Integrations → WhatsApp → Manage, and files will go out with it.")
            label = unit_label(unit) if unit else file.filename
            params = [entity.first_name, label][: int(mt.get("body_params", 0))]
            return send(i, entity_type, entity, template={**mt, "params": params}, file=file, unit=unit)
        kind_, media = _media(i, file)
        if caption:
            media["caption"] = caption[:1000]
        payload, kind, body = {"to": phone, "type": kind_, kind_: media}, "document", caption
    elif text:
        if not window_open(ws_id, phone):
            raise ApiError(409, "whatsapp_window_closed", f"{entity.name} hasn't messaged you in the last 24 hours, so WhatsApp only allows approved templates. "
                           "Send a template; once they reply you can message freely for 24 hours.")
        payload, kind, body = {"to": phone, "type": "text", "text": {"body": text[:4096], "preview_url": True}}, "text", text[:4096]
    else:
        raise ApiError(422, "validation_error", "Nothing to send.")

    wamid = _post(i, payload)
    user_id = g.user.id if has_request_context() and getattr(g, "user", None) else None
    links = activities.links_for(entity_type, entity)
    m = WhatsAppMessage(workspace_id=ws_id, direction="outbound", status="sent", kind=kind, phone=phone, body=body,
                        template_name=template["name"] if template else None, template_language=template.get("language") if template else None,
                        file_id=file.id if file else None, unit_id=unit.id if unit else None, user_id=user_id, wa_message_id=wamid,
                        data={**data, **({"filename": file.filename, "doc_kind": file.doc_kind} if file else {})}, **links)
    db.session.add(m)
    db.session.flush()
    if file is not None:
        what = DOC_KINDS.get(file.doc_kind or "other", "Document").lower()
        title = f"WhatsApp: sent {what} {file.filename}" + (f" for {unit_label(unit)}" if unit else "")
    elif template:
        title = f"WhatsApp: sent template “{template['name']}”"
    else:
        title = "WhatsApp message sent"
    activities.log_activity("whatsapp", title, workspace_id=ws_id, body=body, user_id=user_id,
                            data={"whatsapp_message_id": str(m.id), "direction": "outbound", **({"file_id": str(file.id)} if file else {})}, **links)
    entity.last_contacted_at = utcnow()
    if unit is not None:
        from app.services import inventory

        inventory.log_event(unit, "whatsapp", note=f"{DOC_KINDS.get(file.doc_kind or 'other', 'Document') if file else 'Message'} sent to {entity.name} on WhatsApp",
                            lead_id=entity.id if entity_type == "lead" else None, contact_id=entity.id if entity_type == "contact" else None)
    return m


def unit_label(unit: Unit) -> str:
    p = db.session.get(Project, unit.project_id)
    return f"{unit.name}{f', {p.name}' if p else ''}"


def unit_documents(unit: Unit) -> list[FileAsset]:
    """Documents on the unit itself first, then the project's (brochures usually live on the project)."""
    from sqlalchemy import or_

    rows = db.session.query(FileAsset).filter(FileAsset.workspace_id == unit.workspace_id, FileAsset.deleted_at.is_(None),
                                              or_(FileAsset.unit_id == unit.id, (FileAsset.project_id == unit.project_id) & FileAsset.unit_id.is_(None))) \
        .order_by(FileAsset.unit_id.is_(None), FileAsset.created_at.desc()).limit(50).all()
    return rows


# ---- inbound webhook ---------------------------------------------------------------------------------------------

def integration_for_token(token: str) -> Integration | None:
    if not token or len(token) < 16:
        return None
    return db.session.query(Integration).filter(Integration.provider == "whatsapp", Integration.config["webhook_token"].astext == token).first()


def valid_signature(i: Integration, raw: bytes, header: str | None) -> bool:
    secret = integrations.get_creds(i).get("app_secret")
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


def _inbound_text(m: dict) -> tuple[str, str]:
    t = m.get("type")
    if t == "text":
        return "text", m["text"].get("body", "")
    if t == "button":
        return "text", m["button"].get("text", "")
    if t == "interactive":
        it = m["interactive"]
        return "text", (it.get("button_reply") or it.get("list_reply") or {}).get("title", "")
    if t in ("image", "document", "video", "audio", "sticker"):
        media = m.get(t, {})
        label = {"image": "Photo", "document": "Document", "video": "Video", "audio": "Voice note", "sticker": "Sticker"}[t]
        return ("image" if t == "image" else "document" if t == "document" else "other"), media.get("caption") or f"[{label}{': ' + media['filename'] if media.get('filename') else ''}]"
    if t == "location":
        loc = m["location"]
        return "other", f"[Location: {loc.get('name') or ''} {loc.get('latitude')},{loc.get('longitude')}]".replace("  ", " ")
    if t == "reaction":
        return "other", f"Reacted {m['reaction'].get('emoji', '')}"
    return "other", f"[{t or 'message'}]"


def handle_webhook(i: Integration, payload: dict) -> dict:
    """Process one Meta webhook delivery. Idempotent: Meta retries, and duplicate message IDs are ignored."""
    ws_id = i.workspace_id
    phone_number_id = integrations.get_creds(i).get("phone_number_id")
    stats = {"messages": 0, "statuses": 0, "new_leads": 0}
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            v = change.get("value") or {}
            if change.get("field") != "messages" or (phone_number_id and (v.get("metadata") or {}).get("phone_number_id") not in (None, phone_number_id)):
                continue
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in v.get("contacts", [])}
            for m in v.get("messages", []):
                if _receive(i, m, names.get(m.get("from"))):
                    stats["messages"] += 1
            for s in v.get("statuses", []):
                stats["statuses"] += _status(ws_id, s)
    i.last_synced_at = utcnow()
    return stats


def _receive(i: Integration, m: dict, profile_name: str | None) -> bool:
    ws_id, wamid = i.workspace_id, m.get("id")
    if not wamid or db.session.query(WhatsAppMessage.id).filter_by(workspace_id=ws_id, wa_message_id=wamid).first():
        return False
    phone = normalize_phone("+" + str(m.get("from", "")))
    if not phone:
        return False
    kind, text = _inbound_text(m)
    found = find_record(ws_id, phone)
    created_lead = False
    if found is None:
        from app.services import audit

        # Never put the number in the name: names are shown to everyone, numbers only to those allowed to see them.
        first, _, last = (profile_name or f"WhatsApp {phone[-4:]}").partition(" ")
        lead = Lead(workspace_id=ws_id, first_name=first[:100], last_name=last[:100] or None, phone=f"+{phone}", source="whatsapp", status="new", tags=["whatsapp"])
        db.session.add(lead)
        db.session.flush()
        activities.log_activity("created", "Lead created from a WhatsApp message", workspace_id=ws_id, lead_id=lead.id, user_id=None)
        audit.record("lead.created", entity_type="lead", entity_id=lead.id, workspace_id=ws_id, actor_type="system", actor_label="WhatsApp",
                     summary=f"Lead “{lead.name}” created from WhatsApp")
        found, created_lead = ("lead", lead), True
    etype, entity = found
    links = activities.links_for(etype, entity)
    when = dt.datetime.fromtimestamp(int(m["timestamp"]), dt.timezone.utc) if str(m.get("timestamp", "")).isdigit() else utcnow()
    ctx = (m.get("context") or {}).get("id")
    msg = WhatsAppMessage(workspace_id=ws_id, direction="inbound", status="received", kind=kind, phone=phone, body=text[:4096], wa_message_id=wamid,
                          data={"type": m.get("type"), "profile_name": profile_name, **({"reply_to": ctx} if ctx else {})}, **links)
    db.session.add(msg)
    db.session.flush()
    activities.log_activity("whatsapp", f"WhatsApp reply from {entity.name}", workspace_id=ws_id, body=text[:2000], user_id=None, occurred_at=when,
                            data={"whatsapp_message_id": str(msg.id), "direction": "inbound"}, **links)
    from app.services import notifications

    owners = [entity.owner_id] if entity.owner_id else notifications.workspace_admins(ws_id)
    path = f"/app/{'contacts' if etype == 'contact' else 'leads'}/{entity.id}"
    notifications.notify(ws_id, owners, "whatsapp_reply", f"{'New WhatsApp lead' if created_lead else 'WhatsApp reply'}: {entity.name}", text[:140], path)
    if created_lead:
        from app.services import events

        events.emit("lead.created", {"lead_id": str(entity.id), "name": entity.name, "email": None}, workspace_id=ws_id)
    return True


def _status(ws_id, s: dict) -> int:
    new = s.get("status")
    if new not in STATUS_RANK:
        return 0
    m = db.session.query(WhatsAppMessage).filter_by(workspace_id=ws_id, wa_message_id=s.get("id")).first()
    if m is None or STATUS_RANK.get(new, 0) <= STATUS_RANK.get(m.status, 0):
        return 0
    m.status = new
    if new == "failed":
        err = (s.get("errors") or [{}])[0]
        m.error = ((err.get("error_data") or {}).get("details") or err.get("title") or "Delivery failed")[:400]
        activities.log_activity("whatsapp", "WhatsApp message failed to deliver", workspace_id=ws_id, body=m.error, user_id=None,
                                data={"whatsapp_message_id": str(m.id), "direction": "outbound"}, touch=False,
                                lead_id=m.lead_id, contact_id=m.contact_id, company_id=m.company_id, deal_id=m.deal_id)
    return 1

