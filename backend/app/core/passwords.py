from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_ph = PasswordHasher()
_DUMMY = _ph.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(hash_: str | None, password: str) -> bool:
    """Constant-ish time even for unknown users (verifies against a dummy hash)."""
    try:
        return _ph.verify(hash_ or _DUMMY, password) and hash_ is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hash_: str) -> bool:
    return _ph.check_needs_rehash(hash_)


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("at least 10 characters")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        problems.append("a mix of letters and numbers")
    if password.lower() in {"password123", "1234567890", "qwerty12345", "password1234"}:
        problems.append("something less common")
    return problems
