from __future__ import annotations

from flask import Flask

from app.config import Config


def create_app(config_object: type | None = None) -> Flask:
    from app.core.bootstrap import init_app

    app = Flask(__name__)
    app.config.from_object(config_object or Config)
    init_app(app)
    return app
