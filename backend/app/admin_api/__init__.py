import importlib

from flask import Blueprint, Flask

ADMIN_MODULES = ["auth", "platform", "accounts", "billing"]


def register_admin(app: Flask) -> None:
    for name in ADMIN_MODULES:
        mod = importlib.import_module(f"app.admin_api.{name}")
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if isinstance(obj, Blueprint) and obj.name not in app.blueprints and getattr(obj, "import_name", "") == mod.__name__:
                app.register_blueprint(obj)
