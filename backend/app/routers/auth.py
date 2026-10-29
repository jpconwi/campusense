"""
routers/auth.py - "Continue with Google" (OAuth 2.0 / OpenID Connect), role selection, logout.

Google shows its own sign-in page. This app never sees or stores a Google
password. After Google confirms who the person is, we only keep:
Google account ID, name and email (see services/user_service.py).

Flow:  React "Continue with Google" button  ->  GET /api/auth/google
       -> Google -> GET /api/auth/callback -> redirect back to the React app.
"""

from authlib.integrations.starlette_client import OAuth, OAuthError
import re
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import config
from app.database import SessionLocal, get_db
from app.security import (NAV, authenticated_only, csrf_protect, ensure_csrf_token,
                          get_current_user, is_admin_email, is_nemsu_email)
from app.services import registration_verification_service, room_service, user_service
from app.services.common import ValidationError, clean_text

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
    return "/admin" if role == "admin" else "/"   # students/instructors land on their dashboard (Home)


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
async def google_login(request: Request, purpose: str = "login"):
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        return _to_login(request, "not_configured")
    is_registration = purpose == "register"
    request.session["auth_purpose"] = "student_registration" if is_registration else "login"
    redirect_uri = f"{config.PUBLIC_URL}/api/auth/callback"
    # hd = hint so Google shows NEMSU accounts first. The REAL check is below.
    params = {"prompt": "select_account"}
    if not is_registration:
        params["hd"] = config.ALLOWED_DOMAIN
    return await oauth.google.authorize_redirect(request, redirect_uri, **params)


def _finish_login(info, allow_personal_registration=False):
    """Server-side NEMSU checks + create/update the account. Returns (result, user_id, role)."""
    email = (info.get("email") or "").strip().lower()
    hosted_domain = (info.get("hd") or "").strip().lower()

    if not info.get("sub") or not info.get("email_verified") or email.count("@") != 1:
        return "wrong_account", None, None

    name = (info.get("name") or email.split("@")[0]).strip()[:120]
    is_nemsu = is_nemsu_email(email)
    is_admin = is_admin_email(email)
    if hosted_domain and hosted_domain != config.ALLOWED_DOMAIN and is_nemsu:
        return "wrong_account", None, None

    if not is_nemsu and not is_admin:
        if allow_personal_registration and email.rsplit("@", 1)[-1] != "gmail.com":
            return "personal_only", None, None
        if not allow_personal_registration:
            return "wrong_account", None, None
        with SessionLocal() as db:
            existing = (user_service.get_by_google_id(db, info["sub"])
                        or user_service.get_by_email(db, email))
            if existing is None:
                return "registration_required", None, None
            if existing.approval_status == "Pending":
                return "approval_pending", None, None
            if existing.approval_status == "Rejected":
                return "approval_rejected", None, None
            if not existing.is_active:
                return "deactivated", None, None
            user = user_service.login_user(db, info["sub"], name, email, False)
            return "ok", user.id, user.role

    with SessionLocal() as db:
        user = user_service.login_user(db, info["sub"], name, email, is_admin)
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

    info = token.get("userinfo") or {}
    purpose = request.session.pop("auth_purpose", "login")
    is_registration = purpose == "student_registration"
    result, user_id, role = await run_in_threadpool(
        _finish_login, info, allow_personal_registration=is_registration)
    if result == "registration_required":
        request.session.clear()
        request.session["student_registration"] = {
            "google_id": info["sub"], "email": info["email"].strip().lower(),
            "google_name": (info.get("name") or "").strip()[:120],
        }
        request.session["student_registration_started_at"] = int(time.time())
        return RedirectResponse("/register", status_code=302)
    if result != "ok":
        return _to_login(request, {
            "approval_pending": "approval_pending",
            "approval_rejected": "approval_rejected",
        }.get(result, result))

    request.session.clear()                      # new session after login
    request.session["user_id"] = user_id
    return RedirectResponse(_landing(role), status_code=302)


@router.post("/student-registration")
async def student_registration(request: Request, full_name: str = Form(...),
                               student_id: str = Form(...),
                               school_id_document: UploadFile = File(None),
                               school_id_back_document: UploadFile = File(None),
                               cor_document: UploadFile = File(None),
                               ai_review_consent: str = Form(""),
                               db: Session = Depends(get_db)):
    """Submit camera-captured or selected ID/COR images for admin review."""
    identity = request.session.get("student_registration")
    started = request.session.get("student_registration_started_at", 0)
    if not identity or time.time() - int(started) > 15 * 60:
        request.session.pop("student_registration", None)
        request.session.pop("student_registration_started_at", None)
        raise HTTPException(401, "Your registration session expired. Start again with personal Gmail.")
    email = identity.get("email", "")
    if email.rsplit("@", 1)[-1].lower() != "gmail.com":
        raise HTTPException(400, "Student registration requires a verified personal Gmail account.")

    name = clean_text(full_name, "Full name", 120)
    school_id = clean_text(student_id, "School ID", 50)
    if len(name) < 3:
        raise ValidationError("Enter your full name as shown on your school ID or COR.")
    if len(school_id) < 3:
        raise ValidationError("Enter a valid NEMSU school ID number.")
    async def read_scan(upload, label):
        if upload is None or not upload.filename:
            return None
        data = await upload.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(413, f"The {label} image must be 5 MB or smaller.")
        signatures = (("image/jpeg", data.startswith(b"\xff\xd8\xff")),
                      ("image/png", data.startswith(b"\x89PNG\r\n\x1a\n")),
                      ("image/webp", len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"))
        content_type = next((kind for kind, valid in signatures if valid), None)
        if not content_type:
            raise ValidationError(f"Choose or capture a valid JPG, PNG, or WEBP {label} image.")
        filename = re.sub(r"[^A-Za-z0-9._-]", "_", upload.filename.replace("\\", "/").rsplit("/", 1)[-1])[:200]
        return {"data": data, "content_type": content_type, "filename": filename}

    id_scan = await read_scan(school_id_document, "school ID")
    id_back_scan = await read_scan(school_id_back_document, "school ID back")
    cor_scan = await read_scan(cor_document, "COR")
    if not id_scan and not cor_scan:
        raise ValidationError("Capture or choose an image of the ID front or COR. The ID back alone is not enough.")

    ai_note = "AI visual review not requested; administrator must inspect the documents manually."
    if ai_review_consent.lower() == "true":
        ai_note = await run_in_threadpool(
            registration_verification_service.review_note,
            (id_scan["data"], id_scan["content_type"]) if id_scan else None,
            (id_back_scan["data"], id_back_scan["content_type"]) if id_back_scan else None,
            (cor_scan["data"], cor_scan["content_type"]) if cor_scan else None,
        )

    # Keep the existing primary document slot compatible with earlier pending accounts.
    primary = id_scan or cor_scan
    user_service.submit_student_registration(
        db, identity["google_id"], name, email, school_id,
        primary["data"], primary["content_type"], primary["filename"],
        document_kind="school_id" if id_scan else "cor",
        cor_document=cor_scan["data"] if id_scan and cor_scan else None,
        cor_content_type=cor_scan["content_type"] if id_scan and cor_scan else None,
        cor_filename=cor_scan["filename"] if id_scan and cor_scan else None,
        id_back_document=id_back_scan["data"] if id_back_scan else None,
        id_back_content_type=id_back_scan["content_type"] if id_back_scan else None,
        id_back_filename=id_back_scan["filename"] if id_back_scan else None,
        ai_note=ai_note)
    request.session.clear()
    return {"success": True,
            "message": "Your student registration is pending admin review. You can sign in after it is approved."}


@router.get("/student-registration")
def student_registration_status(request: Request):
    identity = request.session.get("student_registration")
    started = request.session.get("student_registration_started_at", 0)
    if not identity or time.time() - int(started) > 15 * 60:
        raise HTTPException(401, "Your registration session expired. Start again with personal Gmail.")
    return {"email": identity.get("email", "")}


# ---------------------------------------------------------- role selection
class RoleBody(BaseModel):
    role: str = ""


@router.post("/role")
def select_role(body: RoleBody, user=Depends(authenticated_only), db: Session = Depends(get_db)):
    if user.role is not None:                    # already chosen (or admin)
        return {"role": user.role, "next": _landing(user.role)}
    if not user_service.set_role_first_time(db, user.id, body.role):
        raise HTTPException(400, "Please select Student or Instructor.")
    return {"role": body.role, "next": _landing(body.role)}


# ----------------------------------------------------------------- logout
@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"success": True}
