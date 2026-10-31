"""
routers/mobile_auth.py - sign-in AND registration for the Flutter Android app.

The website uses a browser redirect + session cookie. A native app cannot do
that, so it signs in with the Google Android SDK, sends the resulting ID token
here, and gets back a signed bearer token to send as `Authorization: Bearer ...`.

All the NEMSU rules are the SAME code the website uses (_finish_login).
This router has no CSRF dependency on purpose: it sets no cookie and relies on
no ambient credentials - the Google ID token in the body is the credential.

CHANGES vs. the previous version (all additive, web site untouched):
  * POST /api/auth/mobile/google accepts an optional  purpose: "register".
    With it, a personal Gmail that has no account yet gets
    200 {"status": "registration_required", "email", "google_name"} (no token)
    instead of a 403, so the app can show the registration form.
  * POST /api/auth/mobile/register/student     (multipart, mirrors /api/auth/student-registration)
  * POST /api/auth/mobile/register/instructor  (multipart, mirrors /api/auth/instructor-registration)
    Both re-verify the Google ID token (sent as the `id_token` form field) instead of
    reading the cookie session the website uses.
"""

import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import config
from app.database import get_db
from app.routers.auth import _finish_login
from app.security import MESSAGE_WRONG_ACCOUNT, create_mobile_token
from app.services import registration_verification_service, user_service
from app.services.common import ValidationError, clean_text
from app.services.google_token import InvalidGoogleToken, verify_google_id_token

router = APIRouter(prefix="/api/auth/mobile", tags=["mobile-auth"])

MAX_SCAN_BYTES = 5 * 1024 * 1024

# result codes from _finish_login that mean "stop, show this message"
_BLOCKED = {
    "wrong_account": (403, MESSAGE_WRONG_ACCOUNT),
    "deactivated": (403, "This account has been deactivated."),
    "approval_pending": (403, "Your registration is waiting for admin approval. Try signing in again after it is approved."),
    "approval_rejected": (403, "Your registration was not approved. Please contact the NEMSU administrator."),
    "personal_only": (403, "Personal registration requires a verified Gmail account."),
}


class GoogleTokenBody(BaseModel):
    id_token: str = ""
    purpose: str = "login"            # "login" (default) or "register"


async def _verified_claims(id_token):
    if not config.SECRET_KEY or not config.GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Mobile sign-in is not configured on the server.")
    try:
        return await run_in_threadpool(verify_google_id_token, id_token)
    except InvalidGoogleToken:
        raise HTTPException(401, "Google sign-in could not be verified. Please try again.")
    except Exception as error:               # e.g. Google's key server unreachable
        print("MOBILE LOGIN ERROR:", repr(error))
        raise HTTPException(503, "Sign-in is temporarily unavailable. Please try again.")


@router.post("/google")
async def mobile_google_login(body: GoogleTokenBody):
    info = await _verified_claims(body.id_token)
    registering = body.purpose == "register"

    result, user_id, role = await run_in_threadpool(
        _finish_login, info, allow_personal_registration=registering)

    if result == "registration_required":
        return {"status": "registration_required",
                "email": (info.get("email") or "").strip().lower(),
                "google_name": (info.get("name") or "").strip()[:120]}
    if result in _BLOCKED:
        code, message = _BLOCKED[result]
        raise HTTPException(code, message)

    return {
        "status": "ok",
        "token": create_mobile_token(user_id),
        "token_type": "Bearer",
        "expires_in": config.MOBILE_TOKEN_DAYS * 24 * 3600,
        "role": role,                         # None -> app must show role selection
    }


# ---------------------------------------------------------------- registration
async def _personal_gmail_identity(id_token):
    """Verified Google identity that is allowed to register (personal Gmail only)."""
    info = await _verified_claims(id_token)
    email = (info.get("email") or "").strip().lower()
    if (not info.get("sub") or not info.get("email_verified")
            or email.count("@") != 1 or email.rsplit("@", 1)[-1] != "gmail.com"):
        raise HTTPException(400, "Registration requires a verified personal Gmail account.")
    return {"google_id": info["sub"], "email": email}


async def _read_scan(upload, label):
    if upload is None or not upload.filename:
        return None
    data = await upload.read(MAX_SCAN_BYTES + 1)
    if len(data) > MAX_SCAN_BYTES:
        raise HTTPException(413, f"The {label} image must be 5 MB or smaller.")
    signatures = (("image/jpeg", data.startswith(b"\xff\xd8\xff")),
                  ("image/png", data.startswith(b"\x89PNG\r\n\x1a\n")),
                  ("image/webp", len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"))
    content_type = next((kind for kind, valid in signatures if valid), None)
    if not content_type:
        raise ValidationError(f"Choose or capture a valid JPG, PNG, or WEBP {label} image.")
    filename = re.sub(r"[^A-Za-z0-9._-]", "_",
                      upload.filename.replace("\\", "/").rsplit("/", 1)[-1])[:200]
    return {"data": data, "content_type": content_type, "filename": filename}


@router.post("/register/extract-student-info")
async def extract_mobile_student_info(id_token: str = Form(...), consent: str = Form(...),
                                      scan_document: UploadFile = File(...)):
    await _personal_gmail_identity(id_token)
    if consent.lower() != "true":
        raise HTTPException(400, "Consent is required before AI can read document fields.")
    scan = await _read_scan(scan_document, "student ID or COR")
    result = await run_in_threadpool(
        registration_verification_service.extract_student_identity,
        (scan["data"], scan["content_type"]))
    return {"success": True, **result,
            "message": "Check the detected values before submitting." if result["full_name"] or result["student_id"]
            else "Could not read the name or student ID clearly. You can enter them manually."}


@router.post("/register/student")
async def mobile_student_registration(
        id_token: str = Form(...), full_name: str = Form(...), student_id: str = Form(...),
        school_id_document: UploadFile = File(None),
        school_id_back_document: UploadFile = File(None),
        cor_document: UploadFile = File(None),
        ai_review_consent: str = Form(""),
        db: Session = Depends(get_db)):
    identity = await _personal_gmail_identity(id_token)

    name = clean_text(full_name, "Full name", 120)
    school_id = clean_text(student_id, "School ID", 50)
    if len(name) < 3:
        raise ValidationError("Enter your full name as shown on your school ID or COR.")
    if len(school_id) < 3:
        raise ValidationError("Enter a valid NEMSU school ID number.")

    id_scan = await _read_scan(school_id_document, "school ID")
    id_back_scan = await _read_scan(school_id_back_document, "school ID back")
    cor_scan = await _read_scan(cor_document, "COR")
    if not id_scan and not cor_scan:
        raise ValidationError("Capture or choose an image of the ID front or COR. The ID back alone is not enough.")

    ai_note = "AI visual review not requested; administrator must inspect the documents manually."
    auto_approve = False
    if ai_review_consent.lower() == "true":
        ai_note, auto_approve = await run_in_threadpool(
            registration_verification_service.review_documents,
            (id_scan["data"], id_scan["content_type"]) if id_scan else None,
            (id_back_scan["data"], id_back_scan["content_type"]) if id_back_scan else None,
            (cor_scan["data"], cor_scan["content_type"]) if cor_scan else None,
        )

    primary = id_scan or cor_scan
    user_service.submit_student_registration(
        db, identity["google_id"], name, identity["email"], school_id,
        primary["data"], primary["content_type"], primary["filename"],
        document_kind="school_id" if id_scan else "cor",
        cor_document=cor_scan["data"] if id_scan and cor_scan else None,
        cor_content_type=cor_scan["content_type"] if id_scan and cor_scan else None,
        cor_filename=cor_scan["filename"] if id_scan and cor_scan else None,
        id_back_document=id_back_scan["data"] if id_back_scan else None,
        id_back_content_type=id_back_scan["content_type"] if id_back_scan else None,
        id_back_filename=id_back_scan["filename"] if id_back_scan else None,
        ai_note=ai_note, auto_approve=auto_approve)

    if auto_approve:
        return {"success": True, "approval_status": "Approved",
                "message": "Your document passed the visual screening and your student account is active. Sign in to continue."}
    return {"success": True, "approval_status": "Pending",
            "message": "Your documents need manual admin review. Your account will remain pending until it is approved."}


@router.post("/register/instructor")
async def mobile_instructor_registration(
        id_token: str = Form(...), full_name: str = Form(...),
        instructor_id: str = Form(...), department: str = Form(...),
        db: Session = Depends(get_db)):
    identity = await _personal_gmail_identity(id_token)

    name = clean_text(full_name, "Full name", 120)
    employee_id = clean_text(instructor_id, "Instructor ID number", 50)
    unit = clean_text(department, "Department", 120)
    if len(name) < 3:
        raise ValidationError("Enter your full name.")
    if len(employee_id) < 3:
        raise ValidationError("Enter a valid instructor ID number.")
    if len(unit) < 2:
        raise ValidationError("Enter your department.")

    user_service.submit_instructor_registration(
        db, identity["google_id"], name, identity["email"], employee_id, unit)
    return {"success": True,
            "message": "Your instructor registration is pending admin review. You can sign in after it is approved."}
