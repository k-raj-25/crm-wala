"""Security headers, CSRF double-submit protection, shared cookie helpers."""
from __future__ import annotations

import hmac

from flask import Flask, Response, current_app, request

from app.core.errors import ApiError

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# The impersonation exchange authenticates with a one-time secret code rather than ambient cookies, so there is nothing to forge.
CSRF_EXEMPT_PREFIXES = ("/api/v1/billing/webhooks/", "/api/v1/public/", "/api/v1/inbound/", "/api/v1/auth/impersonate/exchange", "/healthz")
# Each realm only trusts its own cookies: on a shared host (localhost in dev) the other app's cookies are also sent.
REALMS = {"admin": ("/admin-api/", ("adm_access", "adm_refresh"), "adm_csrf"), "user": ("/", ("crm_access", "crm_refresh"), "crm_csrf")}


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
        realm = REALMS["admin"] if request.path.startswith("/admin-api/") else REALMS["user"]
        if not any(c in request.cookies for c in realm[1]):
            return None  # no ambient credentials => nothing to forge
        cookie = request.cookies.get(realm[2]) or ""
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
