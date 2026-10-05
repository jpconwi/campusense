"""
routers/mobile_auth.py - sign-in for the Flutter Android app.

The website uses a browser redirect + session cookie. A native app cannot do
that, so it signs in with the Google Android SDK, sends the resulting ID token
here, and gets back a signed bearer token to send as `Authorization: Bearer ...`.

All the NEMSU rules are the SAME code the website uses (_finish_login).
This router has no CSRF dependency on purpose: it sets no cookie and relies on
no ambient credentials - the Google ID token in the body is the credential.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app import config
from app.routers.auth import _finish_login
from app.security import MESSAGE_WRONG_ACCOUNT, create_mobile_token
from app.services.google_token import InvalidGoogleToken, verify_google_id_token

router = APIRouter(prefix="/api/auth/mobile", tags=["mobile-auth"])


class GoogleTokenBody(BaseModel):
    id_token: str = ""


@router.post("/google")
async def mobile_google_login(body: GoogleTokenBody):
    if not config.SECRET_KEY or not config.GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Mobile sign-in is not configured on the server.")
    try:
        info = await run_in_threadpool(verify_google_id_token, body.id_token)
    except InvalidGoogleToken:
        raise HTTPException(401, "Google sign-in could not be verified. Please try again.")
    except Exception as error:               # e.g. Google's key server unreachable
        print("MOBILE LOGIN ERROR:", repr(error))
        raise HTTPException(503, "Sign-in is temporarily unavailable. Please try again.")

    result, user_id, role = await run_in_threadpool(_finish_login, info)
    if result == "wrong_account":
        raise HTTPException(403, MESSAGE_WRONG_ACCOUNT)
    if result == "deactivated":
        raise HTTPException(403, "This account has been deactivated.")

    return {
        "token": create_mobile_token(user_id),
        "token_type": "Bearer",
        "expires_in": config.MOBILE_TOKEN_DAYS * 24 * 3600,
        "role": role,                         # None -> app must show role selection
    }
