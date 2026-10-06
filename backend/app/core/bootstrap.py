"""Application wiring: extensions, middleware, blueprints, CLI."""
from __future__ import annotations

import logging
import uuid

from flask import Flask, g, request
from werkzeug.middleware.proxy_fix import ProxyFix

from app.extensions import db, limiter, migrate


def init_app(flask_app: Flask) -> None:
    if flask_app.config["ENV"] == "production":
        from app.config import Config

        Config.validate_for_production()

    logging.basicConfig(
        level=flask_app.config.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]
    flask_app.url_map.strict_slashes = False

    db.init_app(flask_app)
    from app import models as _models  # noqa: F401  (register models for migrations)

    migrate.init_app(flask_app, db, directory="migrations")
    limiter.init_app(flask_app)

    from app.core import tenant
    from app.core.cli import register_cli
    from app.core.errors import register_error_handlers
    from app.core.security import register_security

    register_security(flask_app)
    register_error_handlers(flask_app)
    register_cli(flask_app)

    from app.api import register_blueprints

    register_blueprints(flask_app)

    @flask_app.before_request
    def _request_id():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]

    @flask_app.after_request
    def _echo_request_id(resp):
        resp.headers["X-Request-ID"] = getattr(g, "request_id", "")
        return resp

    @flask_app.teardown_request
    def _reset_tenant(exc):
        if exc:
            db.session.rollback()
        tenant._ctx.set(tenant.TenantCtx())
