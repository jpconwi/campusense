"""
services/google_token.py - verify a Google ID token sent by the Android app.

The native Google sign-in gives the app an ID token (a signed JWT). We never
trust it blindly: the signature is checked against Google's public keys, and
the issuer, audience (our own GOOGLE_CLIENT_ID), and expiry are validated.
Only RS256 is accepted. The NEMSU-domain rules are applied afterwards by the
same function the website uses (routers/auth.py::_finish_login).
"""

import threading
import time

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from authlib.jose.errors import JoseError

from app import config

JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ["https://accounts.google.com", "accounts.google.com"]
_CACHE_SECONDS = 3600

_jwt = JsonWebToken(["RS256"])
_lock = threading.Lock()
_cache = {"jwks": None, "fetched_at": 0.0}


class InvalidGoogleToken(Exception):
    """The ID token is missing, expired, forged, or meant for another app."""


_MIN_REFRESH_SECONDS = 60       # a forged token must not make us hammer Google


def _fetch_jwks(force=False):
    with _lock:
        age = time.time() - _cache["fetched_at"]
        stale = _cache["jwks"] is None or age >= _CACHE_SECONDS
        if stale or (force and age >= _MIN_REFRESH_SECONDS):
            response = httpx.get(JWKS_URL, timeout=10)
            response.raise_for_status()
            _cache["jwks"] = response.json()
            _cache["fetched_at"] = time.time()
        return _cache["jwks"]


def _decode(id_token, jwks):
    claims = _jwt.decode(
        id_token, JsonWebKey.import_key_set(jwks),
        claims_options={
            "iss": {"essential": True, "values": ISSUERS},
            "aud": {"essential": True, "value": config.GOOGLE_CLIENT_ID},
            "exp": {"essential": True},
            "sub": {"essential": True},
        })
    claims.validate(leeway=60)
    return dict(claims)


def verify_google_id_token(id_token):
    """Return the verified claims (sub, email, email_verified, name, hd ...)."""
    id_token = (id_token or "").strip()
    if not id_token or not config.GOOGLE_CLIENT_ID:
        raise InvalidGoogleToken("missing token")
    try:
        try:
            return _decode(id_token, _fetch_jwks())
        except (ValueError, JoseError):
            # Google rotates its signing keys: retry once with a fresh key set.
            return _decode(id_token, _fetch_jwks(force=True))
    except (ValueError, JoseError) as error:
        raise InvalidGoogleToken(str(error)) from error
