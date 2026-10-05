"""
routers/admin_login.py - admin sign-in with email + password.

Address in the browser:  /admin/login/<ADMIN_LOGIN_SECRET>
Anyone who uses a wrong secret just gets a normal 404.
"""

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.security import csrf_protect, get_current_user
from app.services import admin_auth_service as admin_auth, user_service

router = APIRouter(prefix="/api/admin/login", tags=["admin-login"],
                   dependencies=[Depends(csrf_protect)])

WRONG = "Wrong email or password."


def _check_secret(secret):
    if not hmac.compare_digest(secret.encode(), config.ADMIN_LOGIN_SECRET.encode()):
        raise HTTPException(404, "That page was not found.")


@router.get("/{secret}")
def login_page_check(secret: str, user=Depends(get_current_user)):
    """The React login page calls this first, so a wrong secret shows the normal 404 page."""
    _check_secret(secret)
    return {"ok": True, "already_admin": bool(user is not None and user.role == "admin")}


class LoginBody(BaseModel):
    email: str = ""
    password: str = ""


@router.post("/{secret}")
def login(secret: str, body: LoginBody, request: Request, db: Session = Depends(get_db)):
    _check_secret(secret)

    email = body.email.strip().lower()[:200]
    password = body.password[:200]
    ip = request.client.host if request.client else "?"

    if admin_auth.is_locked(ip, email):
        raise HTTPException(429, "Too many wrong tries. Please wait 15 minutes and try again.")
    if not admin_auth.verify(db, email, password):
        admin_auth.record_failure(ip, email)
        raise HTTPException(401, WRONG)

    row = user_service.login_admin_password(db, email)
    if not row.is_active:
        raise HTTPException(401, WRONG)

    admin_auth.clear_failures(ip, email)
    request.session.clear()                          # fresh session after login
    request.session["user_id"] = row.id
    return {"success": True, "next": "/admin"}
