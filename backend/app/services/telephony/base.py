"""What a calling provider has to do for CRM-Wala, so Exotel today and Knowlarity / Twilio later plug in the same way.

The CRM never shows a client's number to the employee: the provider calls both sides from the company number
(the "ExoPhone" on Exotel) and bridges them. Webhooks from the provider land on
/api/v1/inbound/calls/<webhook_token>/<hook>, and the adapter turns them into the small records below.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from flask import Request, Response


@dataclass
class Leg:
    """One webhook from the provider about a call: an inbound call asking where to ring, or a status update."""

    call_sid: str
    from_number: str | None = None  # E.164 digits, no "+"
    to_number: str | None = None
    status: str | None = None  # ringing|in_progress|completed|missed|failed
    answered_number: str | None = None  # the number that picked up (the employee's phone)
    duration: int | None = None
    recording_url: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class Dial:
    """Who to ring for a call, in order. The first that answers gets the call."""

    numbers: list[str]  # E.164 digits, no "+"
    caller_id: str  # what the person being rung sees: always the company number
    record: bool = True
    ring_seconds: int = 30
    greeting: str | None = None  # spoken to the client while we ring
    status_url: str | None = None  # where the provider reports when each ring / conversation starts and ends


class Provider:
    key: str = ""
    name: str = ""
    # Fields the admin fills in when connecting; `secret` ones are never sent back to the browser.
    fields: list[dict] = []
    # Webhook names the admin pastes into the provider's console, with what each one is for.
    hooks: dict[str, str] = {}

    def verify(self, creds: dict) -> str:
        """Check the credentials with the provider and return a label for the connection ("Exotel · 080 4719 0000")."""
        raise NotImplementedError

    def start_call(self, creds: dict, *, agent: str, client: str, status_url: str, record: bool, ring_seconds: int, ref: str) -> str:
        """Ring the employee first, then the client, both seeing the company number. Returns the provider's call id."""
        raise NotImplementedError

    def can_transfer(self, creds: dict, direction: str) -> bool:
        """Whether a live call in this direction can be handed to a colleague."""
        return False

    def parse(self, hook: str, req: Request) -> Leg | None:
        raise NotImplementedError

    def dial_response(self, dial: Dial) -> Response:
        """Answer the provider's "who should I ring?" webhook."""
        raise NotImplementedError

    def branch_response(self, go_on: bool) -> Response:
        """Answer a yes/no webhook in the call flow (is there a hand-over waiting?)."""
        raise NotImplementedError
