from __future__ import annotations

from typing import Any

from flask import jsonify


def ok(data: Any = None, meta: dict | None = None, status: int = 200):
    body: dict[str, Any] = {"data": data}
    if meta is not None:
        body["meta"] = meta
    resp = jsonify(body)
    resp.status_code = status
    return resp


def created(data: Any = None):
    return ok(data, status=201)


def no_content():
    return "", 204
