# Backend changes for the Android app

Additive only – the website's cookie login, CSRF protection and every existing route behave
exactly as before. Adds **no new Python dependency** (uses Authlib, httpx and itsdangerous, which
you already have).

## Apply
From your repo root:
```bash
git apply backend_changes/mobile-auth.patch      # or copy the files under files/ into backend/
```
Restart FastAPI. Optional `.env` setting: `MOBILE_TOKEN_DAYS=14` (default 14).

## What changed
| File | Change |
|---|---|
| `app/routers/mobile_auth.py` (new) | `POST /api/auth/mobile/google` – body `{"id_token": "..."}` → `{"token", "token_type", "expires_in", "role"}` |
| `app/services/google_token.py` (new) | Verifies the Google ID token: RS256 only, Google's public keys (cached), issuer, **audience = your `GOOGLE_CLIENT_ID`**, expiry |
| `app/security.py` | `get_current_user` also accepts `Authorization: Bearer <token>`; `csrf_protect` is skipped only for bearer requests (no cookie ⇒ nothing for CSRF to abuse). If a bearer header is present the cookie is ignored |
| `app/config.py`, `app/main.py` | `MOBILE_TOKEN_DAYS`; register the router |
| `tests/test_mobile_auth.py` (new) | 21 tests: happy path, NEMSU rules, forged/expired/wrong-audience/alg-confusion/`alg:none` tokens, tampered & expired bearer, deactivated user, cookie-vs-bearer precedence, CSRF still enforced for cookies |

The NEMSU rules are not re-implemented: the endpoint calls the website's own `_finish_login`.

## Running the tests
Your `backend/.env` sets `COOKIE_SECURE=true`, which leaks into the test run (conftest doesn't
override it) and makes **all** tests fail over `http://`. Run with:
```bash
COOKIE_SECURE=false pytest -q          # 60 passed (39 existing + 21 new)
```
(Consider adding `"COOKIE_SECURE": "false"` to the `os.environ.update` block in `tests/conftest.py`.)
