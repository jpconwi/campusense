"""
services/admin_auth_service.py - admin email + password sign-in.

The password comes from ADMIN_PASSWORD in backend/.env (never in the code or
GitHub). If that is not set, a salted Argon2 hash saved by scripts/create_admin.py
is used. Only emails listed in ADMIN_EMAILS can have an admin password, and the
allowlist is checked again on every request.
"""

import hmac
import time
from collections import defaultdict

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy.orm import Session

from app import config
from app.models import AdminCredential
from app.security import is_admin_email
from app.services.common import ValidationError, now

_hasher = PasswordHasher()
# used so a wrong email takes as long to check as a wrong password
_DUMMY_HASH = _hasher.hash("not-a-real-password")

_fails = defaultdict(list)       # key -> timestamps of recent wrong tries


def _key(ip, email):
    return f"{ip}|{(email or '').strip().lower()}"


def is_locked(ip, email):
    current = time.time()
    key = _key(ip, email)
    _fails[key] = [t for t in _fails[key] if current - t < config.ADMIN_LOCK_SECONDS]
    return len(_fails[key]) >= config.ADMIN_MAX_FAILS


def record_failure(ip, email):
    _fails[_key(ip, email)].append(time.time())


def clear_failures(ip, email):
    _fails.pop(_key(ip, email), None)


def set_password(db: Session, email, password):
    """Used by scripts/create_admin.py. Raises ValidationError with a clear message."""
    email = (email or "").strip().lower()
    if not is_admin_email(email):
        raise ValidationError("That email is not in ADMIN_EMAILS (backend/.env).")
    if len(password or "") < config.ADMIN_MIN_PASSWORD:
        raise ValidationError(f"Password must be at least {config.ADMIN_MIN_PASSWORD} characters.")
    row = db.get(AdminCredential, email)
    if row is None:
        row = AdminCredential(email=email, password_hash="", updated_at=now())
        db.add(row)
    row.password_hash = _hasher.hash(password)
    row.updated_at = now()
    db.commit()


def _check_hash(stored_hash, password):
    try:
        return _hasher.verify(stored_hash, password or "")
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify(db: Session, email, password):
    """True only if the email is an allowlisted admin AND the password matches.

    ADMIN_PASSWORD in .env is used when it is set. Otherwise the hashed
    password saved by scripts/create_admin.py is used."""
    email = (email or "").strip().lower()
    env_password = config.admin_password()
    if env_password:
        same = hmac.compare_digest((password or "").encode(), env_password.encode())
        return same and is_admin_email(email)
    row = db.get(AdminCredential, email)
    matches = _check_hash(row.password_hash if row else _DUMMY_HASH, password)
    return bool(row) and matches and is_admin_email(email)
