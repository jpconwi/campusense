"""
security.py - who is logged in, and what may they do?

Every permission check happens on the SERVER using the signed session cookie +
the database. The browser can never decide the role (the role sent in
POST /api/auth/role is only used once, to pick student/instructor on first
login, and is validated).

Android app: sends "Authorization: Bearer <token>" (see routers/mobile_auth.py).
Bearer requests skip CSRF (no cookie is involved) and ignore the cookie.

CSRF: the session holds a random token. The React app reads it from
GET /api/auth/me and sends it back in the X-CSRF-Token header on every
POST/PUT/PATCH/DELETE request.
"""

import hmac
import secrets
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.services import user_service

MESSAGE_WRONG_ACCOUNT = "Please use your official NEMSU Google account."
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

NAV = {
    "student": [
        ("Home", "/"), ("Campus AI", "/ai"), ("My Reports", "/reports"),
        ("My Concerns", "/concerns"), ("Feedback", "/feedback"),
        ("Reservations", "/reservations"), ("Profile", "/profile"),
    ],
    "instructor": [
        ("Home", "/"), ("Campus AI", "/ai"), ("My Reports", "/reports"),
        ("Faculty Availability", "/faculty"), ("My Concerns", "/concerns"),
        ("Feedback", "/feedback"), ("Reservations", "/reservations"), ("Profile", "/profile"),
    ],
    "admin": [
        ("Dashboard", "/admin"), ("Campus AI", "/ai"), ("Users", "/admin/users"),
        ("Concerns", "/admin/concerns"), ("Reports", "/admin/reports"),
        ("Faculty Reports", "/admin/faculty"), ("Feedback", "/admin/feedback"),
        ("Reservations", "/admin/reservations"), ("Rooms", "/admin/rooms"),
        ("Campus", "/admin/campus"),
    ],
}


@dataclass
class CurrentUser:
    """Small read-only object describing the logged-in user."""
    id: int
    name: str
    email: str
    role: Optional[str]            # student / instructor / admin / None
    created_at: str
    last_login: str

    @property
    def is_admin(self):
        return self.role == "admin"

    def public(self):
        return {"id": self.id, "name": self.name, "email": self.email, "role": self.role,
                "created_at": self.created_at, "last_login": self.last_login}


# ------------------------------------------------ bearer tokens (Android app)
# The website uses the signed session cookie. The Android app sends
# "Authorization: Bearer <token>" instead. The token only carries the user id;
# role/is_active are always re-read from the database.
def _token_serializer():
    return URLSafeTimedSerializer(config.SECRET_KEY, salt="campusense-mobile-v1")


def create_mobile_token(user_id):
    return _token_serializer().dumps({"uid": int(user_id)})


def bearer_token(request: Request) -> Optional[str]:
    """The bearer token from the Authorization header, or None if not used."""
    header = request.headers.get("authorization") or ""
    if header[:7].lower() == "bearer ":
        return header[7:].strip()
    return None


def _user_id_from_bearer(token):
    if not config.SECRET_KEY:
        return None
    try:
        data = _token_serializer().loads(token, max_age=config.MOBILE_TOKEN_DAYS * 86400)
        return int(data["uid"])
    except (BadSignature, KeyError, TypeError, ValueError):
        return None


# ------------------------------------------------------------- email rules
def is_nemsu_email(email):
    email = (email or "").strip().lower()
    return email.endswith("@" + config.ALLOWED_DOMAIN) and email.count("@") == 1


def is_admin_email(email):
    return (email or "").strip().lower() in config.admin_emails()


# ------------------------------------------------------------ current user
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[CurrentUser]:
    """Load the user from the database using the user id kept in the session."""
    if hasattr(request.state, "current_user"):
        return request.state.current_user

    user = None
    bearer = bearer_token(request)
    if bearer is not None:
        # Bearer present -> ONLY the token counts (the cookie is ignored).
        user_id = _user_id_from_bearer(bearer)
    else:
        user_id = request.session.get("user_id")
    if user_id:
        row = user_service.get_user(db, user_id)
        if row is not None and row.is_active:
            role = row.role
            if is_admin_email(row.email):
                role = "admin"
            elif role == "admin":
                role = None                   # no longer on the allowlist
            user = CurrentUser(
                id=row.id, name=row.name, email=row.email, role=role,
                created_at=row.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                last_login=row.last_login.strftime("%Y-%m-%d %H:%M:%S"))
    request.state.current_user = user
    return user


def authenticated_only(request: Request, user=Depends(get_current_user)) -> CurrentUser:
    """Logged in, but the role may still be missing (used by role selection)."""
    if user is None:
        request.session.clear()
        raise HTTPException(401, "Please sign in.")
    return user


def login_required(request: Request, user=Depends(get_current_user)) -> CurrentUser:
    """Logged in AND role chosen."""
    if user is None:
        request.session.clear()
        raise HTTPException(401, "Please sign in.")
    if user.role is None:
        raise HTTPException(403, "Please select your account type first.")
    return user


def role_required(*roles):
    def dependency(user: CurrentUser = Depends(login_required)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(403, "You do not have permission to do that.")
        return user
    return dependency


def admin_required(user=Depends(get_current_user)) -> CurrentUser:
    """Anyone who is not a signed-in admin gets a plain 404, so the admin API
    cannot even be confirmed by guessing."""
    if user is None or user.role != "admin":
        raise HTTPException(404, "That page was not found.")
    return user


# -------------------------------------------------------------------- CSRF
def ensure_csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def csrf_protect(request: Request):
    """Dependency for routers: unsafe methods must send the session's CSRF token."""
    if request.method in SAFE_METHODS:
        return
    if bearer_token(request) is not None:
        return          # not cookie-based, so there is nothing for CSRF to abuse
    expected = request.session.get("csrf") or ""
    sent = request.headers.get("x-csrf-token") or ""
    if not expected or not hmac.compare_digest(expected.encode(), sent.encode()):
        raise HTTPException(400, "Your session expired. Please refresh the page and try again.")
