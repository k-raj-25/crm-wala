from __future__ import annotations

import importlib

from flask import Flask, jsonify

# Customer API modules (each exposes one or more Blueprints named `bp` / `*_bp`).
CUSTOMER_MODULES = [
    "auth", "workspace", "settings", "team", "leads", "contacts", "companies", "deals", "pipelines", "tasks",
    "interactions", "activity", "analytics", "billing", "data", "automations", "integrations", "ai", "public",
]


def register_blueprints(app: Flask) -> None:
    from flask import Blueprint

    for name in CUSTOMER_MODULES:
        mod = importlib.import_module(f"app.api.v1.{name}")
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if isinstance(obj, Blueprint) and obj.name not in app.blueprints and getattr(obj, "import_name", "") == mod.__name__:
                app.register_blueprint(obj)

    from app.admin_api import register_admin

    register_admin(app)

    @app.get("/healthz")
    def healthz():
        from sqlalchemy import text

        from app.extensions import db

        db.session.execute(text("select 1"))
        return jsonify({"status": "ok"})
