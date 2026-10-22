"""Exotel (exotel.com): Indian virtual numbers ("ExoPhones") with click-to-call and programmable call flows.

Outbound: the Calls/connect API rings the employee first, then the client; both see the ExoPhone. With "client first"
on, the client is rung first and dropped into the CRM's call flow, which is what lets an outbound call be handed over.
Inbound: the ExoPhone's call flow is   Connect (dynamic URL: hook "connect")  ->  Passthru (hook "handover")
                                         ^------------- 200: hand-over waiting ---'    302: Hangup
so after an employee hangs up, the client stays on the line and is rung through to whoever the call was handed to.
Exotel only allows a blind hand-over this way (the employee hangs up, the colleague is rung), which is how it's built.
"""
from __future__ import annotations

import json
import logging

import httpx
from flask import Request, Response, current_app

from app.core.errors import ApiError
from app.services.telephony.base import Dial, Leg, Provider

log = logging.getLogger("app.telephony.exotel")

REGIONS = {"api.in.exotel.com": "Mumbai", "api.exotel.com": "Singapore"}
_DIAL_STATUS = {"completed": "completed", "answered": "in_progress", "in-progress": "in_progress", "ringing": "ringing", "busy": "missed",
                "no-answer": "missed", "canceled": "missed", "failed": "failed"}


def _digits(raw) -> str | None:
    from app.services.whatsapp import normalize_phone

    return normalize_phone(str(raw)) if raw else None


class Exotel(Provider):
    key, name = "exotel", "Exotel"
    fields = [
        {"key": "account_sid", "label": "Account SID", "hint": "Exotel dashboard → Settings → API Settings"},
        {"key": "api_key", "label": "API key"},
        {"key": "api_token", "label": "API token", "secret": True},
        {"key": "subdomain", "label": "Region", "options": [{"value": k, "label": f"{v} ({k})"} for k, v in REGIONS.items()]},
        {"key": "exophone", "label": "Company number (ExoPhone)", "hint": "The virtual number clients see and call back, e.g. 080 4719 0000"},
        {"key": "flow_app_id", "label": "Call flow app ID", "optional": True,
         "hint": "App Bazaar → My Apps: the ID of the CRM flow on your ExoPhone. Needed to ring the client first on outgoing calls."},
    ]
    hooks = {
        "connect": "Connect applet → Configure parameters dynamically → Primary URL",
        "handover": "Passthru after each Connect (200 → another Connect with the URL above, 302 → Hangup)",
        "status": "Status / dial events (filled in automatically)",
    }

    # ---- REST ------------------------------------------------------------------------------------------------

    def _url(self, creds: dict, path: str) -> str:
        host = creds.get("subdomain") or "api.in.exotel.com"
        if host not in REGIONS:
            raise ApiError(422, "validation_error", "Pick your Exotel region.", {"subdomain": "Unknown region"})
        return f"https://{host}/v1/Accounts/{creds['account_sid']}/{path}"

    def _call(self, method: str, creds: dict, path: str, **kw) -> httpx.Response:
        try:
            return httpx.request(method, self._url(creds, path), auth=(creds["api_key"], creds["api_token"]), timeout=15, **kw)
        except httpx.HTTPError:
            raise ApiError(502, "calling_unreachable", "Couldn't reach Exotel. Please try again in a minute.")

    @staticmethod
    def _error(r: httpx.Response) -> str:
        try:
            j = r.json()
            return (j.get("RestException") or {}).get("Message") or r.text[:200]
        except ValueError:
            return r.text[:200]

    def verify(self, creds: dict) -> str:
        r = self._call("GET", creds, "Balance.json")
        if r.status_code in (401, 403):
            raise ApiError(422, "validation_error", "Exotel rejected the API key or token.", {"api_token": self._error(r)})
        if r.status_code >= 400:
            raise ApiError(422, "validation_error", "Exotel didn't recognise this account. Check the Account SID and region.", {"account_sid": self._error(r)})
        num = _digits(creds["exophone"])
        if not num:
            raise ApiError(422, "validation_error", "Enter the ExoPhone with its area code.", {"exophone": "Invalid number"})
        return f"Exotel · +{num}"

    def can_transfer(self, creds: dict, direction: str) -> bool:
        # Outbound calls rung through the call flow (client first) can be handed over; plain click-to-call can't.
        return direction == "inbound" or (direction == "outbound" and bool(creds.get("flow_app_id")) and bool(creds.get("client_first")))

    def start_call(self, creds: dict, *, agent: str, client: str, status_url: str, record: bool, ring_seconds: int, ref: str) -> str:
        client_first = bool(creds.get("flow_app_id")) and bool(creds.get("client_first"))
        data = {"CallerId": creds["exophone"], "TimeOut": str(ring_seconds), "CustomField": ref, "StatusCallback": status_url,
                "StatusCallbackContentType": "application/json", "StatusCallbackEvents[0]": "terminal", "StatusCallbackEvents[1]": "answered"}
        if client_first:
            data.update(From=f"+{client}", Url=f"http://my.exotel.com/{creds['account_sid']}/exoml/start_voice/{creds['flow_app_id']}")
        else:
            data.update(From=f"+{agent}", To=f"+{client}", Record="true" if record else "false")
        r = self._call("POST", creds, "Calls/connect.json", data=data)
        if r.status_code == 401:
            raise ApiError(409, "calling_reconnect", "Exotel rejected the saved API key. Reconnect calling in Integrations.")
        if r.status_code == 403:
            # Not a bad key (that's 401): Exotel refuses the call itself, e.g. a trial account calling a number that
            # isn't verified, KYC pending, or no balance. Exotel's own reason is the useful part.
            log.warning("exotel refused call: %s", r.text[:300])
            raise ApiError(409, "calling_refused", f"Exotel refused the call: {self._error(r)}")
        if r.status_code >= 400:
            raise ApiError(502, "calling_failed", f"Exotel couldn't place the call: {self._error(r)}")
        sid = ((r.json() or {}).get("Call") or {}).get("Sid")
        if not sid:
            raise ApiError(502, "calling_failed", "Exotel didn't return a call id.")
        return sid

    # ---- webhooks --------------------------------------------------------------------------------------------

    def parse(self, hook: str, req: Request) -> Leg | None:
        p = {**req.args.to_dict(), **req.form.to_dict(), **(req.get_json(silent=True) or {})}
        sid = p.get("CallSid") or p.get("call_sid")
        if not sid:
            return None
        frm, to = _digits(p.get("CallFrom") or p.get("From")), _digits(p.get("CallTo") or p.get("To"))
        status = None
        raw_status = (p.get("DialCallStatus") or p.get("Status") or "").strip().lower()
        if hook == "status":
            if (p.get("EventType") or "").lower() == "answered":
                status = "in_progress"
            elif raw_status:
                status = _DIAL_STATUS.get(raw_status, "completed")
        elif hook == "handover" and raw_status:
            status = _DIAL_STATUS.get(raw_status, "completed")
        duration = p.get("ConversationDuration") or p.get("DialCallDuration")
        legs = p.get("Legs") if isinstance(p.get("Legs"), list) else []
        if not duration and legs:
            duration = max((int(x.get("OnCallDuration") or 0) for x in legs), default=0)
        return Leg(call_sid=str(sid), from_number=frm, to_number=to, status=status, answered_number=_digits(p.get("DialWhomNumber")),
                   duration=int(duration) if str(duration or "").isdigit() else None, recording_url=p.get("RecordingUrl") or None,
                   raw={k: v for k, v in p.items() if k in ("Direction", "EventType", "CustomField", "DialCallStatus", "Status", "flow_id")})

    def dial_response(self, dial: Dial) -> Response:
        body: dict = {"fetch_after_attempt": False, "destination": {"numbers": [f"+{n}" for n in dial.numbers]}, "record": dial.record,
                      "recording_channels": "single", "max_ringing_duration": max(10, min(dial.ring_seconds, 60)), "max_conversation_duration": 3600}
        if dial.greeting:
            body["start_call_playback"] = {"playback_to": "caller", "type": "text", "value": dial.greeting[:200]}
        if dial.status_url:
            body["dial_passthru_event_url"] = dial.status_url
        return Response(json.dumps(body), mimetype="application/json")

    def branch_response(self, go_on: bool) -> Response:
        # Exotel's Passthru applet takes the "200" branch on 200 and the "302" branch on a 302.
        if go_on:
            return Response("handover", status=200, mimetype="text/plain")
        r = Response("", status=302)
        r.headers["Location"] = current_app.config["WEB_ORIGIN"]
        return r
