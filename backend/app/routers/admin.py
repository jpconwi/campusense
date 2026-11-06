"""
routers/admin.py - the Admin Dashboard API (/api/admin/...).

Every route here needs the admin role. The role is checked on the server
from the database + ADMIN_EMAILS list, never from the browser. Anyone who is
not a signed-in admin gets a plain 404.
All numbers on the dashboard are real counts from the database.
"""

import json
from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from app import config
from app.database import get_db
from app.models import (AIProviderSetting, AdminActivityLog, CampusDepartment, User,
                        UserDailyActivity, UserPresence)
from app.security import (CurrentUser, admin_required, csrf_protect, is_admin_email,
                          is_nemsu_email, super_admin_required)
from app.services import (announcement_service, campus_service, chart_service, common, concern_service, faculty_service,
                          photo_report_service, registration_help_service, report_service, reservation_service,
                          room_service, user_service)
from app.services.common import ValidationError

# admin_required runs first so non-admins cannot even tell these URLs exist
router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(admin_required), Depends(csrf_protect)])

SECTIONS = {
    "concerns": {"title": "Student Concerns", "image": True, "pdf": True},
    "reports": {"title": "Campus Reports", "image": True, "pdf": True},
    "feedback": {"title": "Feedback", "image": False, "pdf": True},
    "reservations": {"title": "Reservations", "image": False, "pdf": False},
}


def _strings(body):
    """JSON values -> text, so the validators always receive strings."""
    return {str(k): ("" if v is None else str(v)) for k, v in (body or {}).items()}


def _without_sentiment(rows):
    """Keep sentiment metadata out of the administrator interface payloads."""
    return [{k: v for k, v in row.items() if k not in ("sentiment", "sentiment_score")}
            for row in rows]


# --------------------------------------------------------- AI provider chain
@router.get("/ai-status")
def ai_status(_me: CurrentUser = Depends(super_admin_required)):
    """Which AI providers are set up, in the order they are tried. Never shows keys."""
    from app.model import systemAi
    return {"providers": systemAi.chain_status()}


def _urgent_open(db):
    rows = [r for r in common.list_rows(db, "reports") if r["urgent"]
            and r["status"] in ("Pending", "Under Review", "In Progress")]
    return _without_sentiment([photo_report_service.for_admin(r) for r in rows])


# ------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    faculty = faculty_service.load_records(db)
    stats = [
        ["Total Students", user_service.count_role(db, "student")],
        ["Total Instructors", user_service.count_role(db, "instructor")],
        ["Pending Concerns", common.count_rows(db, "concerns", "Pending")],
        ["Total Reports", common.count_rows(db, "reports")],
        ["Pending Reports", common.count_rows(db, "reports", "Pending")],
        ["Urgent Photo Reports (open)", len(_urgent_open(db))],
        ["Resolved Reports", common.count_rows(db, "reports", "Resolved")],
        ["Faculty Reports", len(faculty)],
        ["Total Feedback", common.count_rows(db, "feedback")],
        ["Total Reservations", common.count_rows(db, "reservations")],
    ]
    return {
        "stats": stats,
        "charts": chart_service.dashboard_charts(db),
        "recent_concerns": _without_sentiment(common.list_rows(db, "concerns", status="Pending", limit=5)),
        "recent_reports": _without_sentiment(common.list_rows(db, "reports", status="Pending", limit=5)),
        "urgent_reports": _urgent_open(db)[:5],
    }


@router.get("/user-activity")
def user_activity(_me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    """Recent foreground activity for active student and instructor accounts."""
    now = datetime.utcnow().replace(microsecond=0)
    today = now.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8))).date()
    cutoffs = {"1d": today, "7d": today - timedelta(days=6),
               "30d": today - timedelta(days=29)}
    users = db.scalars(select(User).where(
        User.role.in_(("student", "instructor")), User.is_active.is_(True),
        User.approval_status == "Approved", User.deleted_at.is_(None)
    ).order_by(User.name)).all()
    presence = {row.user_id: row.last_seen_at for row in db.scalars(select(UserPresence)).all()}
    activity = db.scalars(select(UserDailyActivity).where(
        UserDailyActivity.activity_date >= (now - timedelta(days=30)).date()
    )).all()
    totals = {}
    for row in activity:
        values = totals.setdefault(row.user_id, {"1d": 0, "7d": 0, "30d": 0})
        for key, cutoff in cutoffs.items():
            if row.activity_date >= cutoff:
                values[key] += row.active_seconds
    rows = []
    online_cutoff = now - timedelta(seconds=120)
    for person in users:
        seen = presence.get(person.id)
        seconds = totals.get(person.id, {})
        rows.append({
            "id": person.id, "name": person.name, "email": person.email, "role": person.role,
            "online": bool(seen and seen >= online_cutoff),
            "last_seen_at": seen.isoformat() if seen else None,
            "minutes_1d": seconds.get("1d", 0) // 60,
            "minutes_7d": seconds.get("7d", 0) // 60,
            "minutes_30d": seconds.get("30d", 0) // 60,
        })
    # Keep currently online users first, then most recently seen, then name.
    rows.sort(key=lambda row: (not row["online"],
                               -(datetime.fromisoformat(row["last_seen_at"]).timestamp()
                                 if row["last_seen_at"] else 0), row["name"].lower()))
    return {"rows": rows, "online_count": sum(row["online"] for row in rows), "as_of": now.isoformat()}


# -------------------------------------------------------- record lists
@router.get("/records/{kind}")
def records(kind: str, status: Optional[str] = None, urgent: Optional[str] = None,
            me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    if kind not in SECTIONS:
        raise HTTPException(404, "That page was not found.")
    if kind == "reservations" and me.role != "super_admin":
        raise HTTPException(404, "That page was not found.")
    if status and status not in common.TABLE_STATUSES[kind]:
        status = None
    rows = common.list_rows(db, kind, status=status)
    if kind == "concerns":
        for row in rows:
            if row.get("source") == "photo":
                try:
                    row["ai"] = json.loads(row.get("ai_analysis") or "null")
                except ValueError:
                    row["ai"] = None
    if kind == "reports":
        rows = [photo_report_service.for_admin(r) for r in rows]
        for row in rows:
            row["record_kind"] = "problem"
        concerns = common.list_rows(db, "concerns", status=status)
        for row in concerns:
            try:
                row["ai"] = json.loads(row.get("ai_analysis") or "null") if row.get("source") == "photo" else None
            except ValueError:
                row["ai"] = None
            row["record_kind"] = "concern"
            row["report_type"] = row.get("concern_type")
            row["urgent"] = bool(row["ai"] and row["ai"].get("urgent"))
        rows.extend(concerns)
        if urgent == "1":
            rows = [r for r in rows if r["urgent"]]
        open_now = ("Pending", "Under Review", "In Progress")
        # possible hazards that are still open come first (the sort keeps newest-first inside each group)
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        rows.sort(key=lambda r: not (r["urgent"] and r["status"] in open_now))
    rows = _without_sentiment(rows)
    return {
        "kind": kind, "spec": ({**SECTIONS[kind], "title": "Reports and Concerns"}
                                 if kind == "reports" else SECTIONS[kind]), "current": status,
        "urgent_only": urgent == "1",
        "statuses": common.TABLE_STATUSES[kind],
        "columns": [[h, k] for h, k, _ in common.COLUMNS[kind]],
        "rows": rows,
        "assignees": sorted(config.admin_emails() | {name for (name,) in db.query(CampusDepartment.name).all()})
                     if kind in ("reports", "concerns") else [],
    }


class StatusBody(BaseModel):
    status: str = ""


@router.post("/records/{kind}/{row_id}/status")
def change_status(kind: str, row_id: int, body: StatusBody, me: CurrentUser = Depends(admin_required),
                  db: Session = Depends(get_db)):
    if kind not in SECTIONS:
        raise HTTPException(404, "That page was not found.")
    if kind == "reservations" and me.role != "super_admin":
        raise HTTPException(404, "That page was not found.")
    if kind == "reservations":
        reservation_service.change_status(db, row_id, body.status)
    elif not common.update_status(db, kind, row_id, body.status):
        raise ValidationError("Record not found.")
    return {"success": True, "message": f"Status of #{row_id} changed to {body.status}."}


class VerifyBody(BaseModel):
    verification: str = ""
    note: str = ""


class ReportAssignmentBody(BaseModel):
    assigned_admin_email: Optional[str] = None


@router.post("/records/{kind}/{row_id}/assign")
def assign_record(kind: str, row_id: int, body: ReportAssignmentBody,
                  db: Session = Depends(get_db)):
    if kind not in ("reports", "concerns"):
        raise HTTPException(404, "That page was not found.")
    row = db.get(common.MODELS[kind], row_id)
    if row is None:
        raise ValidationError("Report not found.")
    requested = (body.assigned_admin_email or "").strip()
    if not requested:
        row.assigned_admin_email = None
    elif requested.lower() in config.admin_emails():
        row.assigned_admin_email = requested.lower()
    else:
        if "@" in requested:
            raise ValidationError("Choose a configured administrator email or enter a department name.")
        row.assigned_admin_email = common.clean_text(requested, "Department", 120)
    row.updated_at = common.now()
    db.commit()
    return {"success": True, "message": "Report assignment updated."}


class AdminFeedbackBody(BaseModel):
    message: str = ""


@router.post("/records/{kind}/{row_id}/feedback")
def update_reporter_feedback(kind: str, row_id: int, body: AdminFeedbackBody,
                             db: Session = Depends(get_db)):
    if kind not in ("reports", "concerns"):
        raise HTTPException(404, "That page was not found.")
    message = common.clean_text(body.message, "Update", 2000, required=False)
    row = db.get(common.MODELS[kind], row_id)
    if row is None:
        raise ValidationError("Report not found.")
    row.admin_feedback = message or None
    row.updated_at = common.now()
    db.commit()
    return {"success": True, "message": "Reporter update saved."}


@router.post("/reports/{report_id}/assign")
def assign_report(report_id: int, body: ReportAssignmentBody, db: Session = Depends(get_db)):
    """Assign a report to one of the server-configured administrators."""
    from app.models import Report
    row = db.get(Report, report_id)
    if row is None:
        raise ValidationError("Report not found.")
    email = (body.assigned_admin_email or "").strip().lower() or None
    departments = {name for (name,) in db.query(CampusDepartment.name).all()}
    if email is not None and email not in config.admin_emails() and email not in departments:
        raise ValidationError("Choose an administrator or department from the list.")
    row.assigned_admin_email = email
    row.updated_at = common.now()
    db.commit()
    return {"success": True, "message": "Report assignment updated."}


@router.delete("/reports/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db)):
    report_service.delete_report(db, report_id)
    return {"success": True, "message": f"Report #{report_id} deleted."}


@router.delete("/concerns/{concern_id}")
def delete_concern(concern_id: int, db: Session = Depends(get_db)):
    concern_service.delete_concern(db, concern_id)
    return {"success": True, "message": f"Concern #{concern_id} deleted."}


@router.post("/reports/{report_id}/verify")
def verify_photo_report(report_id: int, body: VerifyBody, me: CurrentUser = Depends(admin_required),
                        db: Session = Depends(get_db)):
    """An administrator confirms or rejects what the AI found in a photo report."""
    photo_report_service.verify(db, me, report_id, body.verification, body.note)
    return {"success": True, "message": f"Report #{report_id} marked {body.verification}."}


# ------------------------------------------------------------- faculty
@router.get("/faculty")
def faculty(db: Session = Depends(get_db)):
    return {"rows": list(reversed(faculty_service.load_records(db)))}


@router.post("/faculty/{record_id}/available")
def faculty_available(record_id: int, db: Session = Depends(get_db)):
    if not faculty_service.mark_available_by_id(db, record_id):
        raise ValidationError("Record not found or already available.")
    return {"success": True, "message": "Marked as available."}


# --------------------------------------------------------------- users
@router.get("/users")
def users(_me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    rows = user_service.list_users(db)
    for r in rows:
        r.pop("google_id", None)                 # not needed by the browser
        r.pop("verification_document", None)     # served only by the admin-only file route
        r.pop("verification_cor_document", None)
        r.pop("verification_id_back_document", None)
        r.pop("face_image", None)
        r.pop("face_scan_pdf", None)
        r["has_verification_document"] = bool(r.get("verification_filename"))
        r["has_cor_document"] = bool(r.get("verification_cor_filename"))
        r["has_id_back_document"] = bool(r.get("verification_id_back_filename"))
        r["has_face_image"] = bool(r.get("face_image_filename"))
        r["has_face_scan_pdf"] = bool(r.get("face_scan_pdf_filename"))
        r["is_allowlisted_admin"] = is_admin_email(r["email"])
    return {"rows": rows}


@router.get("/users/{user_id}/verification-document")
def user_verification_document(user_id: int, _me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    row = user_service.get_user(db, user_id)
    if row is None or not row.verification_document or not row.verification_content_type:
        raise HTTPException(404, "Verification document not found.")
    filename = row.verification_filename or "student-verification"
    disposition = "attachment" if row.verification_content_type == "application/pdf" else "inline"
    return Response(row.verification_document, media_type=row.verification_content_type,
                    headers={"Content-Disposition": f'{disposition}; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/users/{user_id}/verification-document/cor")
def user_cor_document(user_id: int, _me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    row = user_service.get_user(db, user_id)
    if row is None or not row.verification_cor_document or not row.verification_cor_content_type:
        raise HTTPException(404, "COR scan not found.")
    filename = row.verification_cor_filename or "student-cor"
    return Response(row.verification_cor_document, media_type=row.verification_cor_content_type,
                    headers={"Content-Disposition": f'inline; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/users/{user_id}/verification-document/id-back")
def user_id_back_document(user_id: int, _me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    row = user_service.get_user(db, user_id)
    if row is None or not row.verification_id_back_document or not row.verification_id_back_content_type:
        raise HTTPException(404, "ID back scan not found.")
    filename = row.verification_id_back_filename or "student-id-back"
    return Response(row.verification_id_back_document, media_type=row.verification_id_back_content_type,
                    headers={"Content-Disposition": f'inline; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/users/{user_id}/face-image")
def user_face_image(user_id: int, _me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    row = user_service.get_user(db, user_id)
    if row is None or not row.face_image or not row.face_image_content_type:
        raise HTTPException(404, "Selfie not found.")
    filename = row.face_image_filename or "applicant-selfie.jpg"
    return Response(row.face_image, media_type=row.face_image_content_type,
                    headers={"Content-Disposition": f'inline; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/users/{user_id}/face-scan-pdf")
def user_face_scan_pdf(user_id: int, _me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    row = user_service.get_user(db, user_id)
    if row is None or not row.face_scan_pdf:
        raise HTTPException(404, "Face scan PDF not found.")
    filename = row.face_scan_pdf_filename or "face-scan.pdf"
    return Response(row.face_scan_pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"',
                             "Cache-Control": "no-store"})


class FaceReviewBody(BaseModel):
    status: str = ""


@router.post("/users/{user_id}/face-review")
def user_face_review(user_id: int, body: FaceReviewBody, _me: CurrentUser = Depends(super_admin_required),
                     db: Session = Depends(get_db)):
    if body.status not in ("Verified", "Rejected"):
        raise ValidationError("Choose Verified or Rejected.")
    row = user_service.get_user(db, user_id)
    if row is None or row.approval_status != "Pending" or not row.face_image:
        raise ValidationError("That pending account has no selfie to review.")
    row.face_review_status = body.status
    db.commit()
    return {"success": True, "message": f"Selfie marked {body.status.lower()}."}


@router.post("/users/{user_id}/approve")
def approve_user_registration(user_id: int, me: CurrentUser = Depends(super_admin_required),
                              db: Session = Depends(get_db)):
    if user_id == me.id or not user_service.approve_personal_registration(db, user_id):
        raise ValidationError("That personal-Gmail registration is not pending or is missing required details.")
    return {"success": True, "message": "Account registration approved."}


@router.post("/users/{user_id}/reject")
def reject_user_registration(user_id: int, me: CurrentUser = Depends(super_admin_required),
                             db: Session = Depends(get_db)):
    if user_id == me.id or not user_service.reject_student_registration(db, user_id):
        raise ValidationError("That student registration is not pending.")
    return {"success": True, "message": "Account registration rejected."}


class RoleBody(BaseModel):
    role: str = ""


class ActiveBody(BaseModel):
    active: bool = True


@router.post("/users/{user_id}/role")
def user_role(user_id: int, body: RoleBody, me: CurrentUser = Depends(super_admin_required),
              db: Session = Depends(get_db)):
    if user_id == me.id:
        raise ValidationError("You cannot change your own role.")
    if not user_service.admin_set_role(db, user_id, body.role):
        raise ValidationError("Could not change that role (admins are set in ADMIN_EMAILS).")
    return {"success": True, "message": "Role updated."}


@router.post("/users/{user_id}/active")
def user_active(user_id: int, body: ActiveBody, me: CurrentUser = Depends(super_admin_required),
                db: Session = Depends(get_db)):
    if user_id == me.id:
        raise ValidationError("You cannot deactivate yourself.")
    if not user_service.set_active(db, user_id, body.active):
        raise ValidationError("Could not change that account.")
    return {"success": True,
            "message": "Account activated." if body.active else "Account deactivated."}


@router.delete("/users/{user_id}")
def user_delete(user_id: int, me: CurrentUser = Depends(super_admin_required),
                db: Session = Depends(get_db)):
    if user_id == me.id or not user_service.soft_delete_user(db, user_id):
        raise ValidationError("That account cannot be deleted.")
    return {"success": True, "message": "Account disabled and scheduled for permanent deletion in 7 days."}


@router.get("/system")
def system_overview(_me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    """System-wide analytics, AI integration health, and privileged action history."""
    from app.model import systemAi
    rows = db.scalars(select(AdminActivityLog).order_by(AdminActivityLog.created_at.desc()).limit(100)).all()
    departments = [{"id": r.id, "name": r.name, "office": r.office}
                   for r in db.scalars(select(CampusDepartment).order_by(CampusDepartment.name)).all()]
    return {
        "role_counts": [[role, user_service.count_role(db, role)]
                        for role in ("student", "instructor", "admin", "super_admin")],
        "record_counts": [[label, common.count_rows(db, table)] for label, table in (
            ("Reports", "reports"), ("Concerns", "concerns"), ("Reservations", "reservations"),
            ("Feedback", "feedback"))],
        "analytics": chart_service.dashboard_charts(db),
        "ai_providers": systemAi.chain_status(),
        "departments": departments,
        "activity": [{"id": r.id, "actor_email": r.actor_email, "action": r.action,
                      "target_email": r.target_email, "details": r.details,
                      "created_at": r.created_at.strftime("%Y-%m-%d %I:%M:%S %p")} for r in rows],
    }


class AccessRoleBody(BaseModel):
    role: str = ""


@router.post("/system/users/{user_id}/role")
def system_user_role(user_id: int, body: AccessRoleBody, me: CurrentUser = Depends(super_admin_required),
                     db: Session = Depends(get_db)):
    if user_id == me.id:
        raise ValidationError("You cannot change your own access level.")
    target = user_service.get_user(db, user_id)
    if target is None or not user_service.super_admin_set_role(db, user_id, body.role):
        raise ValidationError("Choose an approved account and a valid role.")
    db.add(AdminActivityLog(actor_email=me.email, action="role_changed", target_email=target.email,
                            details=f"Role set to {body.role}", created_at=common.now()))
    db.commit()
    return {"success": True, "message": f"{target.email} is now {body.role.replace('_', ' ')}."}


class CreateAdminBody(BaseModel):
    name: str = ""
    email: str = ""
    password: str = ""


@router.post("/system/admins")
def create_admin_account(body: CreateAdminBody, me: CurrentUser = Depends(super_admin_required),
                         db: Session = Depends(get_db)):
    name = common.clean_text(body.name, "Name", 120)
    email = body.email.strip().lower()
    if (len(email) > 255 or any(character.isspace() for character in email)
            or email.count("@") != 1 or not is_nemsu_email(email)):
        raise ValidationError(f"Enter an email address at @{config.ALLOWED_DOMAIN}.")
    if user_service.get_by_email(db, email):
        raise ValidationError("An account already exists for that email.")
    row = User(google_id="admin-provisioned:" + email, name=name, email=email, role="admin",
               approval_status="Approved", registration_type="admin", is_active=True,
               created_at=common.now(), last_login=common.now())
    db.add(row)
    db.flush()
    from app.services import admin_auth_service
    admin_auth_service.set_password(db, email, body.password, commit=False)
    db.add(AdminActivityLog(actor_email=me.email, action="admin_account_created", target_email=email,
                            details="Created report-manager account with password login enabled.", created_at=common.now()))
    db.commit()
    return {"success": True, "message": f"Admin account created for {email}. Password sign-in: {config.ADMIN_LOGIN_URL}"}


@router.delete("/system/admins/{user_id}")
def delete_admin_account(user_id: int, me: CurrentUser = Depends(super_admin_required),
                         db: Session = Depends(get_db)):
    target = user_service.get_user(db, user_id)
    if (target is None or target.role != "admin" or target.id == me.id
            or is_admin_email(target.email)
            or not user_service.soft_delete_admin_account(db, user_id)):
        raise ValidationError("That administrator is protected, missing, or cannot be deleted.")
    db.add(AdminActivityLog(actor_email=me.email, action="admin_account_deleted", target_email=target.email,
                            details="Account disabled; scheduled for deletion after the retention period.",
                            created_at=common.now()))
    db.commit()
    return {"success": True, "message": f"Admin account {target.email} disabled and scheduled for deletion."}


class DepartmentBody(BaseModel):
    name: str = ""
    office: str = ""


@router.post("/system/departments")
def add_department(body: DepartmentBody, me: CurrentUser = Depends(super_admin_required),
                   db: Session = Depends(get_db)):
    name = body.name.strip()[:120]
    office = body.office.strip()[:160] or None
    if len(name) < 2:
        raise ValidationError("Enter a department name.")
    exists = db.scalars(select(CampusDepartment).where(CampusDepartment.name.ilike(name))).first()
    if exists:
        raise ValidationError("That department is already listed.")
    row = CampusDepartment(name=name, office=office)
    db.add(row)
    db.flush()
    db.add(AdminActivityLog(actor_email=me.email, action="department_added", target_email=None,
                            details=f"Added {name}" + (f" ({office})" if office else ""), created_at=common.now()))
    db.commit()
    return {"success": True, "message": "Department added."}


@router.delete("/system/departments/{department_id}")
def delete_department(department_id: int, me: CurrentUser = Depends(super_admin_required),
                      db: Session = Depends(get_db)):
    row = db.get(CampusDepartment, department_id)
    if row is None:
        raise ValidationError("Department not found.")
    name = row.name
    db.delete(row)
    db.add(AdminActivityLog(actor_email=me.email, action="department_removed", details=f"Removed {name}",
                            created_at=common.now()))
    db.commit()
    return {"success": True, "message": "Department removed."}


class ProviderBody(BaseModel):
    enabled: bool = True


@router.post("/system/ai-provider/{provider}")
def update_ai_provider(provider: str, body: ProviderBody, me: CurrentUser = Depends(super_admin_required),
                       db: Session = Depends(get_db)):
    from app.model import systemAi
    if provider not in systemAi.PROVIDER_ORDER:
        raise ValidationError("Unknown AI provider.")
    setting = db.get(AIProviderSetting, provider)
    if setting is None:
        setting = AIProviderSetting(provider=provider, enabled=body.enabled)
        db.add(setting)
    else:
        setting.enabled = body.enabled
    db.add(AdminActivityLog(actor_email=me.email, action="ai_provider_enabled" if body.enabled else "ai_provider_disabled",
                            details=provider, created_at=common.now()))
    db.commit()
    systemAi.set_provider_enabled(provider, body.enabled)
    return {"success": True, "message": f"{provider} {'enabled' if body.enabled else 'disabled'}."}


@router.get("/help-messages")
@router.get("/registration-help", include_in_schema=False)
def registration_help_inbox(_me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    return {"rows": registration_help_service.list_messages(db)}


@router.post("/help-messages/{message_id}/resolve")
@router.post("/registration-help/{message_id}/resolve", include_in_schema=False)
def registration_help_resolve(message_id: int, _me: CurrentUser = Depends(super_admin_required),
                              db: Session = Depends(get_db)):
    if not registration_help_service.resolve_message(db, message_id):
        raise ValidationError("That message is missing or already resolved.")
    return {"success": True, "message": "Applicant message marked as resolved."}


# ------------------------------------------------------ rooms / campus
ROOM_FIELDS = [["room_id", "Room ID", True], ["name", "Name", True], ["building", "Building", False],
               ["room_type", "Type", False], ["capacity", "Capacity", False],
               ["equipment", "Equipment", False], ["status", "Status", False]]
CAMPUS_FIELDS = [["topic", "Topic", True], ["keywords", "Keywords (use ; between them)", True],
                 ["answer", "Answer", True]]


@router.get("/rooms")
def rooms(_me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    return {"title": "Rooms", "fields": ROOM_FIELDS, "rows": room_service.list_rooms(db),
            "empty": "No rooms yet. Add the real rooms so the AI never has to guess."}


@router.post("/rooms")
def rooms_add(body: dict, _me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    room_service.add_room(db, _strings(body))
    return {"success": True, "message": "Room added."}


@router.delete("/rooms/{row_id}")
def rooms_delete(row_id: int, _me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    room_service.delete_room(db, row_id)
    return {"success": True, "message": "Room deleted."}


@router.get("/campus")
def campus(_me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    return {"title": "Campus Information", "fields": CAMPUS_FIELDS,
            "rows": campus_service.list_info(db), "empty": "No campus information yet."}


@router.post("/campus")
def campus_add(body: dict, _me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    campus_service.add_info(db, _strings(body))
    return {"success": True, "message": "Campus information added."}


@router.delete("/campus/{row_id}")
def campus_delete(row_id: int, _me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    campus_service.delete_info(db, row_id)
    return {"success": True, "message": "Campus information deleted."}


# ------------------------------------------------------ announcements
ANNOUNCEMENT_FIELDS = [
    ["title", "Title", True],
    ["category", "Category", True, "select", announcement_service.CATEGORIES],
    ["body", "Message (what the AI tells people)", True, "textarea"],
    ["start_date", "Show from (optional)", False, "date"],
    ["end_date", "Show until (optional)", False, "date"],
]


@router.get("/announcements")
def announcements(db: Session = Depends(get_db)):
    return {"title": "Announcements", "fields": ANNOUNCEMENT_FIELDS,
            "rows": announcement_service.list_all(db),
            "empty": "No announcements yet. Post news, events or champions and the AI will tell users."}


@router.post("/announcements")
def announcements_add(body: dict, db: Session = Depends(get_db)):
    announcement_service.add_announcement(db, _strings(body))
    return {"success": True, "message": "Announcement posted."}


@router.delete("/announcements/{row_id}")
def announcements_delete(row_id: int, db: Session = Depends(get_db)):
    announcement_service.delete_announcement(db, row_id)
    return {"success": True, "message": "Announcement deleted."}
