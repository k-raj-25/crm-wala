from __future__ import annotations

import logging
from typing import Any

from flask import Flask, g, jsonify, request
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

log = logging.getLogger("app.errors")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def bad_request(message: str, code: str = "bad_request", details: Any = None) -> ApiError:
    return ApiError(400, code, message, details)


def unauthorized(message: str = "Authentication required", code: str = "unauthenticated") -> ApiError:
    return ApiError(401, code, message)


def forbidden(message: str = "You don't have permission to do that", code: str = "forbidden") -> ApiError:
    return ApiError(403, code, message)


def not_found(what: str = "Resource") -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def conflict(message: str, code: str = "conflict") -> ApiError:
    return ApiError(409, code, message)


def payment_required(message: str, code: str = "payment_required", details: Any = None) -> ApiError:
    return ApiError(402, code, message, details)


def _body(status: int, code: str, message: str, details: Any = None):
    err: dict[str, Any] = {"code": code, "message": message, "request_id": getattr(g, "request_id", None)}
    if details is not None:
        err["details"] = details
    resp = jsonify({"error": err})
    resp.status_code = status
    return resp


def _pydantic_details(exc: ValidationError) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in exc.errors():
        loc = ".".join(str(p) for p in e["loc"]) or "_"
        msg = e["msg"].removeprefix("Value error, ")
        out.setdefault(loc, msg)
    return out


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return _body(e.status, e.code, e.message, e.details)

    @app.errorhandler(ValidationError)
    def _validation(e: ValidationError):
        return _body(422, "validation_error", "Please check the highlighted fields", _pydantic_details(e))

    @app.errorhandler(HTTPException)
    def _http(e: HTTPException):
        code = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large", 429: "rate_limited"}.get(
            e.code or 500, "http_error"
        )
        msg = "Too many requests. Please slow down." if e.code == 429 else (e.description or e.name)
        return _body(e.code or 500, code, msg)

    @app.errorhandler(Exception)
    def _unhandled(e: Exception):
        from flask import current_app

        from app.extensions import db

        if current_app.testing:  # surface real tracebacks in tests
            raise e
        log.exception("Unhandled error on %s %s", request.method, request.path)
        db.session.rollback()
        try:
            from app.models import ApiErrorLog

            db.session.add(
                ApiErrorLog(
                    method=request.method, path=request.path[:300], status=500, message=repr(e)[:2000],
                    workspace_id=getattr(getattr(g, "workspace", None), "id", None), request_id=getattr(g, "request_id", None),
                )
            )
            db.session.commit()
        except Exception:  # pragma: no cover
            db.session.rollback()
        return _body(500, "internal_error", "Something went wrong on our side. Please try again.")
