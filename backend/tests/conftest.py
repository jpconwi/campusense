"""
Test setup. Runs against a REAL PostgreSQL database (never your real one).

    createdb campusense_test          (or see README "Run the tests")
    TEST_DATABASE_URL=postgresql://campus:campus@localhost:5432/campusense_test pytest -q

Google and the AI model are replaced by fakes, so no internet or API key is needed.
"""

import os
import tempfile
from pathlib import Path

# ---- environment must be set BEFORE the app is imported -------------------
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", "postgresql://campus:campus@localhost:5432/campusense_test")
os.environ.update({
    "GOOGLE_CLIENT_ID": "test-id", "GOOGLE_CLIENT_SECRET": "test-secret",
    "SECRET_KEY": "test-secret-key", "ADMIN_EMAILS": "admin@nemsu.edu.ph",
    "MODEL": "fake", "API_KEY": "fake", "ADMIN_LOGIN_SECRET": "mysecrets-test",
    "ADMIN_PASSWORD": "",
})

import pytest                                              # noqa: E402
from fastapi.testclient import TestClient                  # noqa: E402
from sqlalchemy import text                                # noqa: E402

from app import config                                    # noqa: E402
from app.ai import ai_engine                               # noqa: E402
from app.database import SessionLocal, engine, init_db     # noqa: E402
from app.main import app                                   # noqa: E402
from app.routers import api as api_module                  # noqa: E402
from app.routers.auth import oauth                         # noqa: E402
from app.services import admin_auth_service, campus_service  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="campusense_test_"))
config.REPORTS_DIR = TMP / "reports"
config.UPLOAD_DIR = TMP / "uploads"
config.ensure_folders()
init_db()

GOOGLE = {}
PROMPTS = []


async def _fake_token(request):
    return {"userinfo": dict(GOOGLE)}


oauth.google.authorize_access_token = _fake_token
ai_engine.ask_model = lambda system_prompt, question: (PROMPTS.append(system_prompt) or "MODEL ANSWER")
api_module._too_many = lambda *a, **k: False       # tests ask many questions quickly


class Client:
    """A browser: its own cookie jar, and it always sends the CSRF token."""

    def __init__(self):
        self.http = TestClient(app, raise_server_exceptions=False)

    def csrf(self):
        return self.http.get("/api/auth/me").json()["csrf_token"]

    def get(self, url, **kw):
        return self.http.get(url, **kw)

    def post(self, url, csrf=True, **kw):
        if csrf:
            kw["headers"] = {**kw.get("headers", {}), "X-CSRF-Token": self.csrf()}
        return self.http.post(url, **kw)

    def delete(self, url, **kw):
        return self.http.delete(url, headers={"X-CSRF-Token": self.csrf()}, **kw)

    def google_login(self, email, name="Test User", sub=None, verified=True, hd=None):
        GOOGLE.clear()
        GOOGLE.update({"sub": sub or "sub-" + email, "email": email, "name": name,
                       "email_verified": verified})
        if hd:
            GOOGLE["hd"] = hd
        return self.http.get("/api/auth/callback", follow_redirects=False)

    def me(self):
        return self.get("/api/auth/me").json()

    def ask(self, question):
        return self.post("/api/ask", json={"question": question}).json()


@pytest.fixture(autouse=True)
def clean_database(monkeypatch):
    """Empty every table before each test (campus facts are re-seeded)."""
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE users, admin_credentials, concerns, reports, feedback, reservations, "
            "faculty_reports, rooms, campus_info RESTART IDENTITY CASCADE"))
    with SessionLocal() as db:
        campus_service.seed_if_empty(db)
    admin_auth_service._fails.clear()
    PROMPTS.clear()
    yield


@pytest.fixture
def client():
    return Client


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def prompts():
    return PROMPTS


def make_user(email, role, name=None):
    """Sign in with fake Google and pick a role. Returns the logged-in Client."""
    c = Client()
    c.google_login(email, name or email.split("@")[0].title())
    if role in ("student", "instructor"):
        assert c.post("/api/auth/role", json={"role": role}).status_code == 200
    return c


@pytest.fixture
def student():
    return make_user("sam@nemsu.edu.ph", "student", "Sam Student")


@pytest.fixture
def student2():
    return make_user("alex@nemsu.edu.ph", "student", "Alex Other")


@pytest.fixture
def instructor():
    return make_user("ines@nemsu.edu.ph", "instructor", "Ines Instructor")


@pytest.fixture
def admin():
    return make_user("admin@nemsu.edu.ph", "admin", "Ada Admin")
