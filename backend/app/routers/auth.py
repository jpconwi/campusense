"""
routers/auth.py - "Continue with Google" (OAuth 2.0 / OpenID Connect), role selection, logout.

Google shows its own sign-in page. This app never sees or stores a Google
password. After Google confirms who the person is, we only keep:
Google account ID, name and email (see services/user_service.py).

Flow:  React "Continue with Google" button  ->  GET /api/auth/google
       -> Google -> GET /api/auth/callback -> redirect back to the React app.
"""

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import config
from app.database import SessionLocal, get_db
from app.security import (NAV, authenticated_only, csrf_protect, ensure_csrf_token,
                          get_current_user, is_admin_email, is_nemsu_email)
from app.services import room_service, user_service

router = APIRouter(prefix="/api/auth", tags=["auth"], dependencies=[Depends(csrf_protect)])

oauth = OAuth()
oauth.register(
    name="google",
    client_id=config.GOOGLE_CLIENT_ID,
    client_secret=config.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def _to_login(request: Request, code):
    """Back to the React login page. `code` is a fixed word the page turns into a message."""
    request.session.clear()
    return RedirectResponse(f"/login?error={code}", status_code=302)


def _landing(role):
    if role is None:
        return "/select-role"
    return "/admin" if role == "admin" else "/ai"


# --------------------------------------------------------------- who am I
@router.get("/me")
def me(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Called by the React app on every page load: current user + CSRF token."""
    data = {"user": None, "csrf_token": ensure_csrf_token(request), "nav": [], "facilities": []}
    if user is not None:
        data["user"] = user.public()
        if user.role:
            data["nav"] = [{"label": label, "path": path} for label, path in NAV[user.role]]
            data["facilities"] = room_service.facility_names(db)
    return data


# ------------------------------------------------------------------ login
@router.get("/google")
async def google_login(request: Request):
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        return _to_login(request, "not_configured")
    redirect_uri = f"{config.PUBLIC_URL}/api/auth/callback"
    # hd = hint so Google shows NEMSU accounts first. The REAL check is below.
    return await oauth.google.authorize_redirect(
        request, redirect_uri, hd=config.ALLOWED_DOMAIN, prompt="select_account")


def _finish_login(info):
    """Server-side NEMSU checks + create/update the account. Returns (result, user_id, role)."""
    email = (info.get("email") or "").strip().lower()
    hosted_domain = (info.get("hd") or "").strip().lower()

    if (not info.get("sub")
            or not info.get("email_verified")
            or not is_nemsu_email(email)
            or (hosted_domain and hosted_domain != config.ALLOWED_DOMAIN)):
        return "wrong_account", None, None

    name = (info.get("name") or email.split("@")[0]).strip()[:120]
    with SessionLocal() as db:
        user = user_service.login_user(db, info["sub"], name, email, is_admin_email(email))
        if not user.is_active:
            return "deactivated", None, None
        role = "admin" if is_admin_email(user.email) else (None if user.role == "admin" else user.role)
        return "ok", user.id, role


@router.get("/callback")
async def callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return _to_login(request, "cancelled")

    result, user_id, role = await run_in_threadpool(_finish_login, token.get("userinfo") or {})
    if result != "ok":
        return _to_login(request, result)

    request.session.clear()                      # new session after login
    request.session["user_id"] = user_id
    return RedirectResponse(_landing(role), status_code=302)


# ---------------------------------------------------------- role selection
class RoleBody(BaseModel):
    role: str = ""


@router.post("/role")
def select_role(body: RoleBody, user=Depends(authenticated_only), db: Session = Depends(get_db)):
    if user.role is not None:                    # already chosen (or admin)
        return {"role": user.role, "next": _landing(user.role)}
    if not user_service.set_role_first_time(db, user.id, body.role):
        raise HTTPException(400, "Please select Student or Instructor.")
    return {"role": body.role, "next": "/ai"}


# ----------------------------------------------------------------- logout
@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"success": True}
