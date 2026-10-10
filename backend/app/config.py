"""
config.py - one place for every setting and file path.

Secrets (database password, API keys, Google credentials) are read from
backend/.env (or real environment variables). They are NEVER written in the
code, the React app or the seed files.
"""

import os
import re
import secrets as _secrets
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent      # .../backend
PROJECT_DIR = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")

# ---------------------------------------------------------------- paths
SEED_DIR = BACKEND_DIR / "seed"
CAMPUS_SEED_CSV = SEED_DIR / "campus_info.csv"
REPORTS_DIR = BACKEND_DIR / "reports"        # generated PDF files
UPLOAD_DIR = BACKEND_DIR / "uploads"         # optional images (private, not served publicly)
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"


# ------------------------------------------------------------- database
def _database_url():
    url = os.getenv("DATABASE_URL", "postgresql://campus:campus@localhost:5432/campusense").strip()
    # SQLAlchemy needs to be told to use the psycopg (v3) driver.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _database_url()

# ------------------------------------------------------------- settings
MODEL = os.getenv("MODEL")
API_KEY = os.getenv("API_KEY")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

SECRET_KEY = os.getenv("SECRET_KEY")

# The address people open in the browser. Google redirects back to
#   <PUBLIC_URL>/api/auth/callback      (add this exact URL in Google Cloud Console)
# Production: the FastAPI port (http://localhost:8000) or your https domain.
# Development with the Vite dev server: http://localhost:5173
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8000").strip().rstrip("/")

# Only accounts ending with this domain may sign in
ALLOWED_DOMAIN = os.getenv("ALLOWED_EMAIL_DOMAIN", "nemsu.edu.ph").strip().lower().lstrip("@")

# Set COOKIE_SECURE=true when the site runs on HTTPS (production)
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() in ("1", "true", "yes")

SESSION_HOURS = 8
# Android app: how long its bearer token stays valid (deactivating a user still
# blocks them immediately, because the user is re-read from the database every request).
MOBILE_TOKEN_DAYS = int(os.getenv("MOBILE_TOKEN_DAYS", "14"))
MAX_UPLOAD_MB = 5


# ---------------------------------------------------- secret admin login URL
# The admin signs in (email + password) at:  /admin/login/<ADMIN_LOGIN_SECRET>
def _load_login_secret():
    """
    1) ADMIN_LOGIN_SECRET in .env wins (8+ characters: letters, numbers, - _ ).
    2) Otherwise a random one is created once and kept in backend/.admin_login_secret.
    """
    raw = (os.getenv("ADMIN_LOGIN_SECRET") or "").strip().strip("/")
    if raw:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,}", raw):
            raise RuntimeError("ADMIN_LOGIN_SECRET must be 8+ characters: "
                               "letters, numbers, - or _ only.")
        if raw.lower() in ("admin", "login", "password"):
            raise RuntimeError("ADMIN_LOGIN_SECRET is too easy to guess. Pick another.")
        return raw
    store = BACKEND_DIR / ".admin_login_secret"
    if store.exists() and store.read_text().strip():
        return store.read_text().strip()
    generated = _secrets.token_urlsafe(18)
    store.write_text(generated)
    print("\nNEW secret admin login created (saved in backend/.admin_login_secret)\n")
    return generated


ADMIN_LOGIN_SECRET = _load_login_secret()
ADMIN_LOGIN_URL = f"/admin/login/{ADMIN_LOGIN_SECRET}"

ADMIN_MIN_PASSWORD = 10                     # characters
ADMIN_MAX_FAILS = 5                         # wrong tries ...
ADMIN_LOCK_SECONDS = 15 * 60                # ... then locked for 15 minutes


def admin_password():
    """Admin password from .env (ADMIN_PASSWORD). Empty = not set."""
    return os.getenv("ADMIN_PASSWORD", "")


def admin_emails():
    """Return the set of authorized administrator emails (lower-case)."""
    raw = os.getenv("ADMIN_EMAILS", "")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def ensure_folders():
    for folder in (UPLOAD_DIR, REPORTS_DIR / "faculty", REPORTS_DIR / "concerns",
                   REPORTS_DIR / "reports", REPORTS_DIR / "feedback"):
        folder.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------- NEMSU knowledge base (collector)
# Public, official sources only. Nothing here is a secret; change them in .env if the
# NEMSU websites move.
NEMSU_NEWS_BASE = os.getenv("NEMSU_NEWS_BASE", "https://nemsu.edu.ph").strip().rstrip("/")
NEMSU_MEMO_BASE = os.getenv("NEMSU_MEMO_BASE", "https://memo.nemsu.edu.ph").strip().rstrip("/")
# how many newsroom list pages one sync looks at (the sync stops earlier when a page has nothing new)
NEMSU_NEWS_PAGES = int(os.getenv("NEMSU_NEWS_PAGES", "3"))
# upper limit of NEW articles saved per sync, so one run stays short
NEMSU_MAX_NEW_PER_SYNC = int(os.getenv("NEMSU_MAX_NEW_PER_SYNC", "25"))
NEMSU_COLLECT_DELAY = float(os.getenv("NEMSU_COLLECT_DELAY", "1.0"))     # seconds between requests
NEMSU_COLLECT_TIMEOUT = float(os.getenv("NEMSU_COLLECT_TIMEOUT", "20"))
# lets a scheduler (Render cron job, cron-job.org) call POST /api/nemsu/sync/scheduled with
# the header  X-Sync-Token: <this value>.  Empty = that route is switched off (404).
NEMSU_SYNC_TOKEN = os.getenv("NEMSU_SYNC_TOKEN", "").strip()
# which sources a sync reads: "news", "memo" or "news,memo". Remove one if its website is down.
NEMSU_SOURCES = [x.strip().lower() for x in os.getenv("NEMSU_SOURCES", "news,memo,page").split(",") if x.strip()]