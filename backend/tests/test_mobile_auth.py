"""Android app sign-in: Google ID token -> bearer token. No internet needed
(Google's public keys are replaced by a test key)."""

import time

import pytest
from authlib.jose import JsonWebKey, JsonWebToken

from app import config
from app.database import SessionLocal
from app.models import User
from app.services import google_token
from tests.conftest import Client

KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "test-kid"})
OTHER_KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "test-kid"})
JWKS = {"keys": [KEY.as_dict(is_private=False)]}


@pytest.fixture(autouse=True)
def fake_google_keys(monkeypatch):
    monkeypatch.setattr(google_token, "_fetch_jwks", lambda force=False: JWKS)


def id_token(email="mia@nemsu.edu.ph", *, key=KEY, alg="RS256", aud=None, iss=None,
             exp_in=3600, verified=True, hd=None, sub=None, name="Mia Student"):
    now = int(time.time())
    payload = {"iss": iss or "https://accounts.google.com", "aud": aud or config.GOOGLE_CLIENT_ID,
               "sub": sub or "sub-" + email, "email": email, "email_verified": verified,
               "name": name, "iat": now, "exp": now + exp_in}
    if hd:
        payload["hd"] = hd
    return JsonWebToken([alg]).encode({"alg": alg, "kid": "test-kid"}, payload, key).decode()


def app_client():
    return Client().http            # fresh client = no cookies, like the phone


def login(c, **kw):
    return c.post("/api/auth/mobile/google", json={"id_token": id_token(**kw)})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- happy path
def test_login_then_role_then_ask_without_csrf_or_cookies():
    c = app_client()
    r = login(c)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "Bearer" and body["role"] is None and body["token"]
    h = auth(body["token"])

    me = c.get("/api/auth/me", headers=h).json()["user"]
    assert me["email"] == "mia@nemsu.edu.ph" and me["role"] is None

    # role not chosen yet -> same rule as the website
    assert c.post("/api/ask", json={"question": "hi"}, headers=h).status_code == 403

    # POST with bearer and NO csrf header works
    assert c.post("/api/auth/role", json={"role": "student"}, headers=h).status_code == 200
    r = c.post("/api/ask", json={"question": "hello"}, headers=h)
    assert r.status_code == 200 and r.json()["type"] == "message" and r.json()["answer"]

    assert c.get("/api/home", headers=h).json()["counts"]["concerns"] == 0


def test_second_login_returns_existing_role():
    c = app_client()
    h = auth(login(c).json()["token"])
    c.post("/api/auth/role", json={"role": "instructor"}, headers=h)
    assert login(c).json()["role"] == "instructor"


# ------------------------------------------------------- NEMSU rules (shared)
@pytest.mark.parametrize("kw", [
    {"email": "someone@gmail.com"},
    {"email": "fake@nemsu.edu.ph.evil.com"},
    {"email": "fake@evilnemsu.edu.ph"},
    {"email": "unverified@nemsu.edu.ph", "verified": False},
    {"email": "wronghd@nemsu.edu.ph", "hd": "other.edu"},
])
def test_non_nemsu_accounts_rejected(kw):
    r = login(app_client(), **kw)
    assert r.status_code == 403 and "NEMSU" in r.json()["error"]
    assert "token" not in r.json()


def test_deactivated_user_cannot_log_in_or_keep_using_token():
    c = app_client()
    token = login(c).json()["token"]
    with SessionLocal() as db:
        db.query(User).update({"is_active": False})
        db.commit()
    assert c.get("/api/auth/me", headers=auth(token)).json()["user"] is None
    r = login(c)
    assert r.status_code == 403


# ------------------------------------------------------- forged / bad tokens
@pytest.mark.parametrize("make", [
    lambda: id_token(aud="someone-elses-client-id"),          # meant for another app
    lambda: id_token(exp_in=-3600),                            # expired
    lambda: id_token(key=OTHER_KEY),                           # wrong signing key
    lambda: id_token(iss="https://evil.example.com"),          # wrong issuer
    lambda: "not.a.jwt",
    lambda: "",
])
def test_bad_google_tokens_rejected(make):
    r = app_client().post("/api/auth/mobile/google", json={"id_token": make()})
    assert r.status_code == 401


def test_hs256_token_signed_with_public_key_is_rejected():
    """Classic algorithm-confusion attack: only RS256 is accepted."""
    now = int(time.time())
    payload = {"iss": "https://accounts.google.com", "aud": config.GOOGLE_CLIENT_ID, "sub": "x",
               "email": "mia@nemsu.edu.ph", "email_verified": True, "exp": now + 3600}
    forged = JsonWebToken(["HS256"]).encode({"alg": "HS256", "kid": "test-kid"}, payload,
                                            "secret").decode()
    assert app_client().post("/api/auth/mobile/google", json={"id_token": forged}).status_code == 401


def test_unsigned_alg_none_token_is_rejected():
    import base64, json
    b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    now = int(time.time())
    forged = (b64({"alg": "none"}) + "." + b64({
        "iss": "https://accounts.google.com", "aud": config.GOOGLE_CLIENT_ID, "sub": "x",
        "email": "mia@nemsu.edu.ph", "email_verified": True, "exp": now + 3600}) + ".")
    assert app_client().post("/api/auth/mobile/google", json={"id_token": forged}).status_code == 401


# ------------------------------------------------------------ bearer handling
def test_garbage_and_tampered_bearer_tokens_get_401():
    c = app_client()
    token = login(c).json()["token"]
    for bad in ("garbage", token[:-3] + "abc", ""):
        r = c.post("/api/ask", json={"question": "hi"}, headers=auth(bad))
        assert r.status_code == 401, bad


def test_expired_bearer_token(monkeypatch):
    c = app_client()
    token = login(c).json()["token"]
    monkeypatch.setattr(config, "MOBILE_TOKEN_DAYS", -1)
    assert c.get("/api/auth/me", headers=auth(token)).json()["user"] is None


def test_bearer_wins_over_cookie_and_bad_bearer_does_not_fall_back_to_cookie(client):
    web = client()                                        # website user with a cookie session
    web.google_login("web@nemsu.edu.ph", "Web User")
    web.post("/api/auth/role", json={"role": "student"})
    assert web.me()["user"]["email"] == "web@nemsu.edu.ph"

    token = login(web.http, email="phone@nemsu.edu.ph").json()["token"]
    assert web.http.get("/api/auth/me", headers=auth(token)).json()["user"]["email"] == \
        "phone@nemsu.edu.ph"
    # a junk bearer header must NOT silently use the cookie session (and so skip CSRF)
    r = web.http.post("/api/ask", json={"question": "hi"}, headers=auth("junk"))
    assert r.status_code == 401


def test_cookie_sessions_still_require_csrf(student):
    r = student.http.post("/api/ask", json={"question": "hi"})      # no CSRF header
    assert r.status_code == 400


def test_logout_with_bearer_is_harmless():
    c = app_client()
    h = auth(login(c).json()["token"])
    assert c.post("/api/auth/logout", headers=h).json() == {"success": True}
