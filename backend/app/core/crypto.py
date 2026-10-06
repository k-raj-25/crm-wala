from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet
from flask import current_app


def _fernet() -> Fernet:
    key = current_app.config.get("ENCRYPTION_KEY")
    if not key:
        # Dev fallback derived from SECRET_KEY. Production config validation requires ENCRYPTION_KEY.
        key = base64.urlsafe_b64encode(hashlib.sha256(current_app.config["SECRET_KEY"].encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def sign(value: str, *, secret: str | None = None) -> str:
    secret = secret or current_app.config["SECRET_KEY"]
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def verify_sig(value: str, signature: str, *, secret: str | None = None) -> bool:
    return hmac.compare_digest(sign(value, secret=secret), signature)
