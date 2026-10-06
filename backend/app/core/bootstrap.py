"""Application wiring: extensions, middleware, blueprints, CLI."""
from __future__ import annotations

import logging
import os
import uuid

from flask import Flask, g, has_request_context, request
from werkzeug.middleware.proxy_fix import ProxyFix

from app.extensions import db, limiter, migrate


class _JsonFormatter(logging.Formatter):
    """One JSON object per line so log shippers (Loki, CloudWatch, Datadog) can index fields without regexes."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        out = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        try:
            out["request_id"] = g.request_id if has_request_context() else None
        except Exception:  # pragma: no cover
            pass
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def _configure_logging(flask_app: Flask) -> None:
    handler = logging.StreamHandler()
    if os.environ.get("LOG_FORMAT", "text" if flask_app.config["ENV"] != "production" else "json") == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(flask_app.config.get("LOG_LEVEL", "INFO"))


def _configure_sentry(flask_app: Flask) -> None:
    """Error tracking is opt-in: set SENTRY_DSN and install sentry-sdk. PII is not sent by default."""
    dsn = flask_app.config.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(dsn=dsn, integrations=[FlaskIntegration()], send_default_pii=False, traces_sample_rate=float(os.environ.get("SENTRY_TRACES", "0.05")),
                        environment=flask_app.config["ENV"])
    except ImportError:  # pragma: no cover
        logging.getLogger(__name__).warning("SENTRY_DSN is set but sentry-sdk is not installed")


def init_app(flask_app: Flask) -> None:
    if flask_app.config["ENV"] == "production":
        from app.config import Config

        Config.validate_for_production()

    _configure_logging(flask_app)
    _configure_sentry(flask_app)
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
