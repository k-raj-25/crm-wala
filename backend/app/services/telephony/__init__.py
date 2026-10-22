"""Calling providers (see base.Provider). One provider is connected per workspace."""
from __future__ import annotations

from app.services.telephony.base import Dial, Leg, Provider
from app.services.telephony.exotel import Exotel

PROVIDERS: dict[str, Provider] = {p.key: p for p in (Exotel(),)}


def adapter(key: str) -> Provider:
    return PROVIDERS[key]


__all__ = ["PROVIDERS", "Dial", "Leg", "Provider", "adapter"]
