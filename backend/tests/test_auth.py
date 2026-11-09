"""Authentication, roles, admin password login, CSRF."""

import pytest

from app import config
from app.models import AdminActivityLog, User
from app.services import admin_auth_service
from app.services.common import ValidationError
from sqlalchemy import select
from tests.conftest import Client, make_user


# ------------------------------------------------------------- Google login
def test_nemsu_login_goes_to_role_selection(client):
    c = client()
    r = c.google_login("student@nemsu.edu.ph", "Sam Student")
    assert r.status_code == 302 and r.headers["location"] == "/select-role"
    user = c.me()["user"]
    assert user["email"] == "student@nemsu.edu.ph" and user["role"] is None


@pytest.mark.parametrize("email,kwargs", [
    ("someone@gmail.com", {}),                                   # not NEMSU
    ("fake@nemsu.edu.ph.evil.com", {}),                          # look-alike domain
    ("fake@evilnemsu.edu.ph", {}),                               # suffix trick
    ("unverified@nemsu.edu.ph", {"verified": False}),            # email not verified
    ("wronghd@nemsu.edu.ph", {"hd": "other.edu"}),               # wrong hosted domain
])
def test_wrong_accounts_are_rejected(client, email, kwargs):
    c = client()
    r = c.google_login(email, **kwargs)
    assert r.status_code == 302 and r.headers["location"] == "/login?error=wrong_account"
    assert c.me()["user"] is None                                # no access
    assert c.post("/api/ask", json={"question": "hi"}).status_code == 401


def test_admin_email_goes_to_dashboard_without_role_selection(client):
    c = client()
    r = c.google_login("admin@nemsu.edu.ph", "Ada Admin")
    assert r.headers["location"] == "/admin"
    assert c.me()["user"]["role"] == "admin"
    assert c.get("/api/admin/dashboard").status_code == 200


def test_role_selection_rules(client):
    c = client()
    c.google_login("new@nemsu.edu.ph")
    assert c.post("/api/ask", json={"question": "hi"}).status_code == 403      # role not chosen
    assert c.post("/api/auth/role", json={"role": "admin"}).status_code == 400  # cannot pick admin
    assert c.me()["user"]["role"] is None
    r = c.post("/api/auth/role", json={"role": "student"})
    assert r.status_code == 200 and r.json()["next"] == "/ai"
    assert c.post("/api/ask", json={"question": "hi"}).status_code == 200
    # the role can not be changed again by the browser
    c.post("/api/auth/role", json={"role": "instructor"})
    assert c.me()["user"]["role"] == "student"


def test_logout_and_returning_user_keeps_role(client):
    c = make_user("sam@nemsu.edu.ph", "student")
    assert c.post("/api/auth/logout").status_code == 200
    assert c.me()["user"] is None
    r = c.google_login("sam@nemsu.edu.ph")
    assert r.headers["location"] == "/ai"                        # no role question again
    assert c.me()["user"]["role"] == "student"


def test_nav_depends_on_role(student, instructor, admin):
    assert "Faculty Availability" not in [n["label"] for n in student.me()["nav"]]
    assert "Faculty Availability" in [n["label"] for n in instructor.me()["nav"]]
    assert "Dashboard" in [n["label"] for n in admin.me()["nav"]]


# ----------------------------------------------------------------- security
def test_missing_csrf_token_is_rejected(student):
    r = student.post("/api/ask", csrf=False, json={"question": "hi"})
    assert r.status_code == 400
    r = student.post("/api/ask", csrf=False, json={"question": "hi"}, headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 400


def test_permissions(client, student, instructor):
    assert student.get("/api/admin/dashboard").status_code == 404           # hidden from students
    assert student.post("/api/admin/records/concerns/1/status", json={"status": "Resolved"}).status_code == 404
    assert instructor.get("/api/admin/dashboard").status_code == 404
    assert student.post("/api/faculty/submit", data={"reason": "x"}).status_code == 403
    assert student.get("/api/me/faculty").status_code == 403
    anon = client()
    assert anon.get("/api/home").status_code == 401
    assert anon.post("/api/ask", json={"question": "hi"}).status_code == 401
    assert anon.get("/api/admin/dashboard").status_code == 404


def test_removed_from_admin_list_loses_access_immediately(admin, monkeypatch):
    assert admin.get("/api/admin/dashboard").status_code == 200
    monkeypatch.setattr(config, "admin_emails", lambda: set())
    assert admin.get("/api/admin/dashboard").status_code == 404
    assert admin.me()["user"]["role"] is None


def _pending_registration(db, *, review_status="Unreviewed", face_review_status="Verified", suffix="one"):
    row = User(google_id=f"registration-{suffix}", name="Pat Applicant", email=f"pat-{suffix}@gmail.com",
               role=None, approval_status="Pending", registration_type="student", student_id="S-123",
               verification_document=b"school-id", verification_content_type="image/png",
               verification_filename="school-id.png", face_image=b"selfie",
               face_image_content_type="image/jpeg", face_image_filename="selfie.jpg",
               face_review_status=face_review_status, review_status=review_status)
    db.add(row)
    db.commit()
    return row


def test_account_approval_refusal_returns_missing_requirements(admin, db):
    row = _pending_registration(db, review_status="Unreviewed", face_review_status="AI Pose Passed")
    response = admin.post(f"/api/admin/accounts/{row.id}/approve", json={})
    assert response.status_code == 400
    assert response.json()["success"] is False
    assert "First-level check not done" in response.json()["missing"]
    assert "Selfie not verified yet" in response.json()["missing"]


def test_ai_pose_passed_alone_does_not_allow_approval(admin, db):
    row = _pending_registration(db, review_status="Checked", face_review_status="AI Pose Passed")
    response = admin.post(f"/api/admin/accounts/{row.id}/approve", json={})
    assert response.status_code == 400
    assert response.json()["missing"] == ["Selfie not verified yet"]


def test_account_queue_returns_review_fields_and_file_flags(admin, db):
    row = _pending_registration(db)
    result = admin.get("/api/admin/accounts").json()["rows"][0]
    assert result["id"] == row.id
    assert result["reviewed_by"] is None and result["reviewed_at"] is None
    assert result["review_note"] is None and result["face_review_status"] == "Verified"
    assert result["has_id_front"] is True and result["has_id_back"] is False
    assert result["has_cor"] is False and result["has_selfie"] is True


def test_rejection_reason_is_saved_and_audited(admin, db):
    row = _pending_registration(db, suffix="reject")
    response = admin.post(f"/api/admin/accounts/{row.id}/reject", json={"reason": "ID details do not match."})
    assert response.status_code == 200
    db.refresh(row)
    assert row.rejection_reason == "ID details do not match."
    event = db.scalar(select(AdminActivityLog).where(AdminActivityLog.action == "account_rejected"))
    assert event and "ID details do not match." in event.details


def test_checked_admin_can_approve_and_old_decision_routes_are_removed(admin, db):
    row = _pending_registration(db, review_status="Checked", face_review_status="Verified")
    assert admin.post(f"/api/admin/accounts/{row.id}/approve", json={}).status_code == 200
    for action in ("approve", "reject", "face-review"):
        assert admin.post(f"/api/admin/users/{row.id}/{action}", json={}).status_code == 404


def test_super_admin_can_skip_check_but_cannot_approve_flagged_account(client, db, monkeypatch):
    monkeypatch.setattr(config, "super_admin_emails", lambda: {"super@nemsu.edu.ph"})
    super_admin = client()
    super_admin.google_login("super@nemsu.edu.ph", "Sam Super")
    assert super_admin.me()["user"]["role"] == "super_admin"
    ready = _pending_registration(db, review_status="Unreviewed", face_review_status="Verified", suffix="ready")
    assert super_admin.post(f"/api/admin/accounts/{ready.id}/approve", json={}).status_code == 200
    flagged = _pending_registration(db, review_status="Flagged", face_review_status="Verified", suffix="flagged")
    response = super_admin.post(f"/api/admin/accounts/{flagged.id}/approve", json={})
    assert response.status_code == 400
    assert "Account was flagged" in response.json()["missing"]


# ------------------------------------------------------- admin password login
SECRET = "/api/admin/login/mysecrets-test"


def test_set_password_rules(db):
    with pytest.raises(ValidationError):
        admin_auth_service.set_password(db, "student@nemsu.edu.ph", "long-enough-password")
    with pytest.raises(ValidationError):
        admin_auth_service.set_password(db, "admin@nemsu.edu.ph", "short")
    admin_auth_service.set_password(db, "admin@nemsu.edu.ph", "long-enough-password")


def test_secret_address(client):
    c = client()
    assert c.get("/api/admin/login/wrong-secret").status_code == 404
    assert c.get("/api/admin/login").status_code == 404
    assert c.get(SECRET).status_code == 200
    assert c.post(SECRET, csrf=False, json={"email": "admin@nemsu.edu.ph", "password": "x"}).status_code == 400


def test_admin_password_login_flow(client, db):
    admin_auth_service.set_password(db, "admin@nemsu.edu.ph", "long-enough-password")
    c = client()
    r = c.post(SECRET, json={"email": "admin@nemsu.edu.ph", "password": "wrong-password"})
    assert r.status_code == 401 and r.json()["error"] == "Wrong email or password."
    assert c.get("/api/admin/dashboard").status_code == 404                 # still no access
    r2 = c.post(SECRET, json={"email": "nobody@nemsu.edu.ph", "password": "wrong-password"})
    assert r2.status_code == 401 and r2.json()["error"] == r.json()["error"]  # same message
    ok = c.post(SECRET, json={"email": "admin@nemsu.edu.ph", "password": "long-enough-password"})
    assert ok.status_code == 200 and ok.json()["next"] == "/admin"
    assert c.get("/api/admin/dashboard").status_code == 200
    assert c.me()["user"]["role"] == "admin"


def test_lockout_after_five_wrong_tries(client, db):
    admin_auth_service.set_password(db, "admin@nemsu.edu.ph", "long-enough-password")
    c = client()
    for _ in range(5):
        assert c.post(SECRET, json={"email": "admin@nemsu.edu.ph", "password": "nope-nope-nope"}).status_code == 401
    r = c.post(SECRET, json={"email": "admin@nemsu.edu.ph", "password": "long-enough-password"})
    assert r.status_code == 429                                              # even the right one


def test_env_admin_password(client, db, monkeypatch):
    admin_auth_service.set_password(db, "admin@nemsu.edu.ph", "old-saved-password")
    monkeypatch.setattr(config, "admin_password", lambda: "env-password-123")
    c = client()
    assert c.post(SECRET, json={"email": "admin@nemsu.edu.ph", "password": "old-saved-password"}).status_code == 401
    assert c.post(SECRET, json={"email": "student@nemsu.edu.ph", "password": "env-password-123"}).status_code == 401
    assert c.post(SECRET, json={"email": "admin@nemsu.edu.ph", "password": "env-password-123"}).status_code == 200
    assert c.get("/api/admin/dashboard").status_code == 200
