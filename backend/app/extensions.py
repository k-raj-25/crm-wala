from __future__ import annotations

from flask import request
from flask_limiter import Limiter
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()


def _client_ip() -> str:
    # ProxyFix has already normalised remote_addr behind a trusted proxy.
    return request.remote_addr or "unknown"


limiter = Limiter(key_func=_client_ip, headers_enabled=True)
