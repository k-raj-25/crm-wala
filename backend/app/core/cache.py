"""Thin Redis helper. All callers must tolerate Redis being unavailable (cache is an optimisation, never a dependency)."""
from __future__ import annotations

import json
import logging
from typing import Any

import redis
from flask import current_app

log = logging.getLogger("app.cache")
_client: redis.Redis | None = None
_failed_at = 0.0


def client() -> redis.Redis | None:
    global _client, _failed_at
    import time

    if _client is not None:
        return _client
    if time.time() - _failed_at < 30:
        return None
    try:
        c = redis.Redis.from_url(current_app.config["REDIS_URL"], socket_timeout=0.5, socket_connect_timeout=0.5, decode_responses=True)
        c.ping()
        _client = c
    except Exception:
        _failed_at = time.time()
        log.warning("redis unavailable; continuing without cache")
    return _client


def get_json(key: str) -> Any | None:
    c = client()
    try:
        v = c.get(key) if c else None
        return json.loads(v) if v else None
    except Exception:
        return None


def set_json(key: str, value: Any, ttl: int = 60) -> None:
    c = client()
    try:
        if c:
            c.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception:
        pass


def set_once(key: str, ttl: int) -> bool:
    """True the first time within `ttl` seconds (SET NX). Returns True if Redis is down so callers still do the work."""
    c = client()
    try:
        return bool(c.set(key, "1", nx=True, ex=ttl)) if c else True
    except Exception:
        return True
