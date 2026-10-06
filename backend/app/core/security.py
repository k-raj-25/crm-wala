"""Security headers, CSRF double-submit protection, shared cookie helpers."""
from __future__ import annotations

import hmac

from flask import Flask, Response, current_app, request

from app.core.errors import ApiError

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT_PREFIXES = ("/api/v1/billing/webhooks/", "/api/v1/public/", "/api/v1/inbound/", "/healthz")
AUTH_COOKIES = ("crm_access", "crm_refresh", "adm_access", "adm_refresh")


def set_cookie(resp: Response, name: str, value: str, *, max_age: int | None, path: str = "/", http_only: bool = True) -> None:
    resp.set_cookie(
        name, value, max_age=max_age, path=path, httponly=http_only, samesite="Lax",
        secure=current_app.config["COOKIE_SECURE"], domain=current_app.config["COOKIE_DOMAIN"],
    )


def clear_cookie(resp: Response, name: str, path: str = "/") -> None:
    resp.delete_cookie(name, path=path, domain=current_app.config["COOKIE_DOMAIN"])


def register_security(app: Flask) -> None:
    @app.before_request
    def _csrf():
        if request.method in SAFE_METHODS:
            return None
        if request.path.startswith(CSRF_EXEMPT_PREFIXES):
            return None
        if request.headers.get("Authorization", "").startswith("Bearer "):
            return None  # non-cookie auth is not CSRF-able
        if not any(c in request.cookies for c in AUTH_COOKIES):
            return None  # no ambient credentials => nothing to forge
        cookie = request.cookies.get("crm_csrf") or request.cookies.get("adm_csrf") or ""
        header = request.headers.get("X-CSRF-Token", "")
        if not cookie or not hmac.compare_digest(cookie, header):
            raise ApiError(403, "csrf_failed", "Security check failed. Please refresh the page and try again.")
        return None

    @app.after_request
    def _headers(resp: Response):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        resp.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        if current_app.config["COOKIE_SECURE"]:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
        if request.path.startswith(("/api/", "/admin-api/")):
            resp.headers["Cache-Control"] = "no-store"
        return resp
