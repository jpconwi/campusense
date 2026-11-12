"""
routers/admin.py - the Admin Dashboard API (/api/admin/...).

Every route here needs the admin role. The role is checked on the server
from the database + ADMIN_EMAILS list, never from the browser. Anyone who is
not a signed-in admin gets a plain 404.
All numbers on the dashboard are real counts from the database.
"""

import csv
import io
import json
import shutil
from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, text
from zoneinfo import ZoneInfo

from app import config
from app.database import engine, get_db
from app.models import (AIProviderSetting, AdminActivityLog, CampusDepartment, User, Feedback,
                        UserDailyActivity, UserPresence, FacultyReport, Reservation, Concern, Report, Room)
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
    return {str(k): ("" if v is None else ", ".join(str(item) for item in v)
                     if isinstance(v, list) else str(v)) for k, v in (body or {}).items()}


def _without_sentiment(rows):
    """Keep sentiment metadata out of the administrator interface payloads."""
    return [{k: v for k, v in row.items() if k not in ("sentiment", "sentiment_score")}
            for row in rows]


def _without_cost_estimates(rows):
    """Keep preliminary repair pricing visible to Super Admins only."""
    safe_rows = []
    private_cost_fields = {"estimated_budget_php_min", "estimated_budget_php_max",
                           "estimate_assumptions", "pricing_basis", "pricing_sources"}
    for row in rows:
        safe = dict(row)
        safe.pop("ai_analysis", None)
        if isinstance(safe.get("ai"), dict):
            safe["ai"] = {key: value for key, value in safe["ai"].items()
                          if key not in private_cost_fields}
        safe_rows.append(safe)
    return safe_rows


def _log_admin_action(db, actor_email, action, target_email, details):
    """Record an account decision so the super admin can see who acted."""
    db.add(AdminActivityLog(actor_email=actor_email, action=action, target_email=target_email,
                            details=details, created_at=common.now()))
    db.commit()


def _account_review_rows(db, is_super_admin=False):
    """Registration accounts (student/instructor) for the first-level check queue."""
    rows = []
    for r in user_service.list_users(db):
        if r.get("deleted_at") or r.get("registration_type") not in ("student", "instructor"):
            continue
        r.pop("google_id", None)
        r["is_nemsu"] = is_nemsu_email(r["email"])
        r["has_verification_document"] = bool(r.get("verification_filename"))
        r["has_cor_document"] = bool(r.get("verification_cor_filename"))
        r["has_id_back_document"] = bool(r.get("verification_id_back_filename"))
        r["has_face_image"] = bool(r.get("face_image_filename"))
        r["has_face_scan_pdf"] = bool(r.get("face_scan_pdf_filename"))
        r["has_id_front"] = r["has_verification_document"] and r.get("verification_document_kind") != "cor"
        r["has_cor"] = r["has_cor_document"] or (r["has_verification_document"] and r.get("verification_document_kind") == "cor")
        r["has_id_back"] = r["has_id_back_document"]
        r["has_selfie"] = r["has_face_image"]
        r["approval_missing"] = user_service.account_approval_missing_values(
            approval_status=r.get("approval_status"), deleted_at=r.get("deleted_at"),
            review_status=r.get("review_status"), face_review_status=r.get("face_review_status"),
            student_id=r.get("student_id"), registration_type=r.get("registration_type"),
            has_verification_document=r["has_verification_document"],
            department=r.get("department"), is_super_admin=is_super_admin)
        rows.append(r)
    return rows


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
def dashboard(me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    faculty = faculty_service.load_records(db)
    pending_accounts = sum(
        row["approval_status"] == "Pending"
        or (row["review_status"] == "Unreviewed" and row["is_nemsu"])
        for row in _account_review_rows(db))
    report_scope = db.query(Report)
    concern_scope = db.query(Concern)
    feedback_scope = db.query(Feedback)
    if me.role == "admin":
        owner = me.email.lower()
        report_scope = report_scope.filter(Report.workflow_review == "Accepted",
                                           Report.assigned_admin_email == owner)
        concern_scope = concern_scope.filter(Concern.workflow_review == "Accepted",
                                             Concern.assigned_admin_email == owner)
        feedback_scope = feedback_scope.filter(Feedback.feedback_scope == "campus")

    counts = {
        "concerns": concern_scope.count(),
        "pending_concerns": concern_scope.filter(Concern.status == "Pending").count(),
        "reports": report_scope.count(),
        "pending_reports": report_scope.filter(Report.status == "Pending").count(),
        "resolved_reports": report_scope.filter(Report.status == "Resolved").count(),
        "feedback": feedback_scope.count(),
        "urgent_reports": len([row for row in _urgent_open(db)
                                if me.role == "super_admin" or (
                                    row.get("workflow_review") == "Accepted"
                                    and (row.get("assigned_admin_email") or "").lower() == me.email.lower())]),
    }
    open_statuses = ("Pending", "Under Review", "In Progress")
    open_reports = report_scope.filter(Report.status.in_(open_statuses))
    open_concerns = concern_scope.filter(Concern.status.in_(open_statuses))
    workload = {
        "open_count": open_reports.count() + open_concerns.count(),
        "completed_count": report_scope.filter(Report.status == "Resolved").count()
        + concern_scope.filter(Concern.status == "Resolved").count(),
        "by_priority": {
            level: open_reports.filter(Report.priority == level).count()
            + open_concerns.filter(Concern.priority == level).count()
            for level in ("Urgent", "High", "Medium", "Low")
        },
    }

    def stat(label, value, href, tone, icon):
        return {"label": label, "value": value, "href": href, "tone": tone, "icon": icon}

    if me.role == "super_admin":
        stats = [
            ["Total Students", user_service.count_role(db, "student")],
            ["Total Instructors", user_service.count_role(db, "instructor")],
            ["Pending Concerns", common.count_rows(db, "concerns", "Pending")],
            ["Total Reports", common.count_rows(db, "reports") + common.count_rows(db, "concerns")],
            ["Pending Reports", common.count_rows(db, "reports", "Pending")],
            ["Urgent Photo Reports (open)", len(_urgent_open(db))],
            ["Resolved Reports", common.count_rows(db, "reports", "Resolved")],
            ["Faculty Reports", len(faculty)],
            ["Total Feedback", common.count_rows(db, "feedback")],
            ["Total Reservations", common.count_rows(db, "reservations")],
            ["Pending Accounts", pending_accounts],
            ["Reports to Finish", workload["open_count"]],
            ["Completed Reports", workload["completed_count"]],
        ]
        stat_cards = [
            stat("Total Students", stats[0][1], "/admin/users?filter=student", "slate", "users"),
            stat("Total Instructors", stats[1][1], "/admin/users?filter=instructor", "slate", "users"),
            stat("Pending Concerns", stats[2][1], "/admin/reports?type=concern&status=Pending", "amber", "concern"),
            stat("Total Reports", stats[3][1], "/admin/reports", "teal", "report"),
            stat("Pending Reports", stats[4][1], "/admin/reports?status=Pending", "amber", "report"),
            stat("Urgent Photo Reports (open)", stats[5][1], "/admin/reports?urgent=1", "red", "alert"),
            stat("Resolved Reports", stats[6][1], "/admin/reports?status=Resolved", "green", "report"),
            stat("Faculty Reports", stats[7][1], "/admin/faculty", "blue", "faculty"),
            stat("Total Feedback", stats[8][1], "/admin/feedback?scope=all", "violet", "feedback"),
            stat("Total Reservations", stats[9][1], "/admin/reservations", "green", "reserve"),
            stat("Pending Accounts", stats[10][1], "/admin/accounts?status=Pending", "amber", "users"),
            stat("Reports to Finish", stats[11][1], "/admin/reports?open_only=true", "amber", "report"),
            stat("Completed Reports", stats[12][1], "/admin/reports?status=Resolved", "green", "report"),
        ]
    else:
        stats = [
            ["Assigned Concerns", counts["concerns"]],
            ["Pending Concerns", counts["pending_concerns"]],
            ["Assigned Reports", counts["reports"]],
            ["Pending Reports", counts["pending_reports"]],
            ["Urgent Photo Reports (open)", counts["urgent_reports"]],
            ["Resolved Reports", counts["resolved_reports"]],
            ["Faculty Reports", len(faculty)],
            ["Campus Feedback", counts["feedback"]],
            ["Total Reservations", common.count_rows(db, "reservations")],
            ["Pending Accounts", pending_accounts],
            ["Reports to Finish", workload["open_count"]],
            ["Completed Reports", workload["completed_count"]],
        ]
        stat_cards = [
            stat("Assigned Concerns", stats[0][1], "/admin/reports?type=concern", "blue", "concern"),
            stat("Pending Concerns", stats[1][1], "/admin/reports?type=concern&status=Pending", "amber", "concern"),
            stat("Assigned Reports", stats[2][1], "/admin/reports?type=problem", "teal", "report"),
            stat("Pending Reports", stats[3][1], "/admin/reports?type=problem&status=Pending", "amber", "report"),
            stat("Urgent Photo Reports (open)", stats[4][1], "/admin/reports?urgent=1", "red", "alert"),
            stat("Resolved Reports", stats[5][1], "/admin/reports?type=problem&status=Resolved", "green", "report"),
            stat("Faculty Reports", stats[6][1], "/admin/faculty", "blue", "faculty"),
            stat("Campus Feedback", stats[7][1], "/admin/feedback?scope=campus", "violet", "feedback"),
            stat("Total Reservations", stats[8][1], "/admin/reservations", "green", "reserve"),
            stat("Pending Accounts", stats[9][1], "/admin/accounts?status=Pending", "amber", "users"),
            stat("Reports to Finish", stats[10][1], "/admin/reports?open_only=true", "amber", "report"),
            stat("Completed Reports", stats[11][1], "/admin/reports?status=Resolved", "green", "report"),
        ]
    recent_reports = common.list_rows(db, "reports", status="Pending")
    recent_concerns = common.list_rows(db, "concerns", status="Pending")
    urgent_reports = _urgent_open(db)
    if me.role == "admin":
        assigned = lambda row: row.get("workflow_review") == "Accepted" and \
            (row.get("assigned_admin_email") or "").lower() == me.email.lower()
        recent_reports = [row for row in recent_reports if assigned(row)]
        recent_concerns = [row for row in recent_concerns if assigned(row)]
        urgent_reports = _without_cost_estimates([row for row in urgent_reports if assigned(row)])
        recent_reports = _without_cost_estimates(recent_reports)
        recent_concerns = _without_cost_estimates(recent_concerns)
    recent_reports = recent_reports[:5]
    recent_concerns = recent_concerns[:5]
    urgent_reports = urgent_reports[:5]
    return {
        "stats": stats,
        "stat_cards": stat_cards,
        "charts": chart_service.dashboard_charts(db),
        "recent_concerns": _without_sentiment(recent_concerns),
        "recent_reports": _without_sentiment(recent_reports),
        "urgent_reports": urgent_reports,
        "workload": workload,
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
            scope: Optional[str] = None, page: int = Query(1, ge=1),
            page_size: int = Query(100, ge=1, le=250), search: str = "",
            record_type: str = "", priority: str = "", open_only: bool = False,
            me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    if kind not in SECTIONS:
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
    elif kind == "concerns":
        for row in rows:
            try:
                row["ai"] = json.loads(row.get("ai_analysis") or "null") if row.get("source") == "photo" else None
            except ValueError:
                row["ai"] = None
            row["urgent"] = bool(row["ai"] and row["ai"].get("urgent"))
    if kind == "feedback":
        if me.role == "admin":
            rows = [row for row in rows if row.get("feedback_scope") == "campus"]
        if scope == "campus":
            rows = [row for row in rows if row.get("feedback_scope") == "campus"]
        elif scope == "suggestions":
            rows = [row for row in rows if row.get("feedback_scope") == "campus"
                    and row.get("feedback_type") == "Suggestion"]
        elif scope == "system":
            rows = [row for row in rows if row.get("feedback_scope") == "system"]
        elif scope == "technical":
            rows = [row for row in rows if row.get("feedback_scope") == "technical"]
        elif scope == "system-technical":
            rows = [row for row in rows if row.get("feedback_scope") in ("system", "technical")]
    if kind in ("reports", "concerns") and me.role == "admin":
        rows = [r for r in rows if r.get("workflow_review") == "Accepted"
                and (r.get("assigned_admin_email") or "").lower() == me.email.lower()]
        rows = _without_cost_estimates(rows)
    rows = _without_sentiment(rows)
    if kind == "reports" and record_type in ("concern", "problem"):
        rows = [row for row in rows if row.get("record_kind") == record_type]
    if priority in ("Urgent", "High", "Medium", "Low"):
        rows = [row for row in rows if row.get("priority", "Medium") == priority]
    if open_only:
        rows = [row for row in rows if row.get("status") in ("Pending", "Under Review", "In Progress")]
    if kind in ("reports", "concerns"):
        priority_order = {"Urgent": 0, "High": 1, "Medium": 2, "Low": 3}
        rows.sort(key=lambda row: priority_order.get(row.get("priority", "Medium"), 2))
    if search.strip():
        term = search.strip().casefold()[:120]
        searchable_fields = ("id", "reporter_name", "reporter_email", "location", "area", "room",
                             "description", "report_type", "concern_type", "status", "assigned_admin_email")
        rows = [row for row in rows if any(term in str(row.get(field) or "").casefold()
                                           for field in searchable_fields)]
    total = len(rows)
    rows = rows[(page - 1) * page_size:page * page_size]
    assignees = []
    if kind in ("reports", "concerns") and me.role == "super_admin":
        admins = db.scalars(select(User).where(User.role == "admin").order_by(User.name)).all()
        presence = {row.user_id: row.last_seen_at for row in db.scalars(select(UserPresence)).all()}
        now_utc = datetime.utcnow().replace(microsecond=0)
        for admin in admins:
            seen = presence.get(admin.id)
            account_active = bool(admin.is_active and admin.deleted_at is None
                                  and admin.approval_status == "Approved")
            assignees.append({
                "id": admin.id, "name": admin.name, "email": admin.email,
                "account_active": account_active,
                "online": bool(account_active and seen and seen >= now_utc - timedelta(seconds=120)),
                "last_active_at": (seen.isoformat() + "Z" if seen else
                                   admin.last_login.replace(tzinfo=ZoneInfo("Asia/Manila")).isoformat()),
            })
        assignees.sort(key=lambda row: (not row["online"], row["name"].lower()))
    return {
        "kind": kind, "spec": ({**SECTIONS[kind], "title": "Reports and Concerns"}
                                 if kind == "reports" else SECTIONS[kind]), "current": status,
        "urgent_only": urgent == "1",
        "statuses": common.TABLE_STATUSES[kind],
        "columns": [[h, k] for h, k, _ in common.COLUMNS[kind]],
        "rows": rows,
        "pagination": {"page": page, "page_size": page_size, "total": total,
                       "pages": max(1, (total + page_size - 1) // page_size)},
        "assignees": assignees,
    }


class StatusBody(BaseModel):
    status: str = ""
    note: str = ""


@router.post("/records/{kind}/{row_id}/status")
def change_status(kind: str, row_id: int, body: StatusBody, me: CurrentUser = Depends(admin_required),
                  db: Session = Depends(get_db)):
    if kind not in SECTIONS:
        raise HTTPException(404, "That page was not found.")
    if kind in ("reports", "concerns"):
        row = db.get(common.MODELS[kind], row_id)
        if row is None:
            raise ValidationError("Report not found.")
        if me.role != "admin" or row.workflow_review != "Accepted" \
                or (row.assigned_admin_email or "").lower() != me.email.lower():
            raise HTTPException(403, "Only the assigned administrator can update this report.")
        if body.status not in common.TABLE_STATUSES[kind]:
            raise ValidationError("Invalid status.")
        row.status = body.status
        row.updated_at = common.now()
        db.commit()
    elif kind == "feedback":
        row = db.get(common.MODELS["feedback"], row_id)
        if row is None:
            raise ValidationError("Feedback not found.")
        if me.role == "admin" and row.feedback_scope != "campus":
            raise HTTPException(403, "Admins can update campus feedback only.")
        if me.role == "admin" and body.status == "Forwarded":
            raise ValidationError("Use the forward action to send feedback to the Super Admin.")
        if not common.update_status(db, kind, row_id, body.status):
            raise ValidationError("Feedback not found.")
    elif kind == "reservations":
        row = db.get(common.MODELS["reservations"], row_id)
        previous = row.status if row else None
        reservation_service.change_status(db, row_id, body.status, me.email, body.note)
        _log_admin_action(db, me.email, "reservation_status_changed", row.requester_email,
                          f"Reservation #{row_id} changed from {previous} to {body.status}."
                          + (f" Note: {body.note.strip()[:350]}" if body.note.strip() else ""))
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
                  me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    if kind not in ("reports", "concerns"):
        raise HTTPException(404, "That page was not found.")
    row = db.get(common.MODELS[kind], row_id)
    if row is None:
        raise ValidationError("Report not found.")
    requested = (body.assigned_admin_email or "").strip().lower()
    if row.workflow_review != "Accepted":
        raise ValidationError("Accept the report before assigning it.")
    assignee = db.scalars(select(User).where(User.email == requested, User.role == "admin")).first()
    if (assignee is None or not assignee.is_active or assignee.deleted_at is not None
            or assignee.approval_status != "Approved"):
        raise ValidationError("That administrator account is inactive and cannot be assigned reports.")
    row.assigned_admin_email = requested
    row.updated_at = common.now()
    db.commit()
    return {"success": True, "message": "Report assignment updated."}


class AdminFeedbackBody(BaseModel):
    message: str = ""


@router.post("/records/{kind}/{row_id}/feedback")
def update_reporter_feedback(kind: str, row_id: int, body: AdminFeedbackBody,
                             me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    if kind not in ("reports", "concerns"):
        raise HTTPException(404, "That page was not found.")
    message = common.clean_text(body.message, "Update", 2000, required=False)
    row = db.get(common.MODELS[kind], row_id)
    if row is None:
        raise ValidationError("Report not found.")
    if me.role != "admin" or row.workflow_review != "Accepted" \
            or (row.assigned_admin_email or "").lower() != me.email.lower():
        raise HTTPException(403, "Only the assigned administrator can update the reporter.")
    row.admin_feedback = message or None
    row.updated_at = common.now()
    db.commit()
    return {"success": True, "message": "Reporter update saved."}


@router.post("/feedback/{feedback_id}/response")
def respond_to_feedback(feedback_id: int, body: AdminFeedbackBody,
                        me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    row = db.get(common.MODELS["feedback"], feedback_id)
    if row is None:
        raise ValidationError("Feedback not found.")
    if me.role == "admin" and row.feedback_scope != "campus":
        raise HTTPException(403, "Admins can respond to campus feedback only.")
    row.admin_response = common.clean_text(body.message, "Response", 2000, required=False) or None
    row.updated_at = common.now()
    db.commit()
    return {"success": True, "message": "Feedback response saved."}


@router.post("/feedback/{feedback_id}/forward")
def forward_feedback(feedback_id: int, me: CurrentUser = Depends(admin_required),
                     db: Session = Depends(get_db)):
    if me.role != "admin":
        raise HTTPException(403, "Only campus admins can forward feedback.")
    row = db.get(common.MODELS["feedback"], feedback_id)
    if row is None or row.feedback_scope != "campus":
        raise ValidationError("Only campus feedback can be forwarded.")
    row.feedback_scope = "system"
    row.forwarded_to_super_admin = True
    row.forwarded_by = me.email
    row.forwarded_at = common.now()
    row.status = "Forwarded"
    row.updated_at = common.now()
    db.commit()
    return {"success": True, "message": "Feedback forwarded to the Super Admin."}


class ReportDecisionBody(BaseModel):
    decision: str
    note: str = ""


@router.post("/records/{kind}/{row_id}/decision")
def decide_report(kind: str, row_id: int, body: ReportDecisionBody,
                  me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    if kind not in ("reports", "concerns"):
        raise HTTPException(404, "That page was not found.")
    if body.decision not in ("Accepted", "Rejected"):
        raise ValidationError("Choose accept or reject.")
    row = db.get(common.MODELS[kind], row_id)
    if row is None:
        raise ValidationError("Report not found.")
    note = common.clean_text(body.note, "Review note", 500, required=False) or None
    row.workflow_review = body.decision
    row.workflow_review_note = note
    row.workflow_reviewed_by = me.email
    row.workflow_reviewed_at = common.now()
    row.assigned_admin_email = None
    if body.decision == "Rejected":
        row.status = "Rejected"
    elif row.status == "Rejected":
        row.status = "Pending"
    row.updated_at = common.now()
    db.commit()
    return {"success": True, "message": f"Report {body.decision.lower()} by Super Admin."}


class ReportPriorityBody(BaseModel):
    priority: str = "Medium"


@router.post("/records/{kind}/{row_id}/priority")
def set_report_priority(kind: str, row_id: int, body: ReportPriorityBody,
                        me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    if kind not in ("reports", "concerns"):
        raise HTTPException(404, "That page was not found.")
    if body.priority not in ("Urgent", "High", "Medium", "Low"):
        raise ValidationError("Choose Urgent, High, Medium, or Low priority.")
    row = db.get(common.MODELS[kind], row_id)
    if row is None:
        raise ValidationError("Report not found.")
    row.priority = body.priority
    row.updated_at = common.now()
    db.commit()
    _log_admin_action(db, me.email, "report_priority_changed", row.reporter_email,
                      f"{kind.rstrip('s').capitalize()} #{row_id} priority set to {body.priority}.")
    return {"success": True, "message": f"Priority set to {body.priority}."}


@router.post("/reports/{report_id}/assign")
def assign_report(report_id: int, body: ReportAssignmentBody,
                  me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    """Assign a report to one of the server-configured administrators."""
    from app.models import Report
    row = db.get(Report, report_id)
    if row is None:
        raise ValidationError("Report not found.")
    email = (body.assigned_admin_email or "").strip().lower()
    if row.workflow_review != "Accepted":
        raise ValidationError("Accept the report before assigning it.")
    assignee = db.scalars(select(User).where(User.email == email, User.role == "admin")).first()
    if (assignee is None or not assignee.is_active or assignee.deleted_at is not None
            or assignee.approval_status != "Approved"):
        raise ValidationError("That administrator account is inactive and cannot be assigned reports.")
    row.assigned_admin_email = email
    row.updated_at = common.now()
    db.commit()
    return {"success": True, "message": "Report assignment updated."}


@router.delete("/reports/{report_id}")
def delete_report(report_id: int, me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    row = db.get(common.MODELS["reports"], report_id)
    if row and me.role != "super_admin" and (row.workflow_review != "Accepted"
            or (row.assigned_admin_email or "").lower() != me.email.lower()):
        raise HTTPException(403, "Only the assigned administrator can manage this report.")
    report_service.delete_report(db, report_id)
    return {"success": True, "message": f"Report #{report_id} deleted."}


@router.delete("/concerns/{concern_id}")
def delete_concern(concern_id: int, me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    row = db.get(common.MODELS["concerns"], concern_id)
    if row and me.role != "super_admin" and (row.workflow_review != "Accepted"
            or (row.assigned_admin_email or "").lower() != me.email.lower()):
        raise HTTPException(403, "Only the assigned administrator can manage this report.")
    concern_service.delete_concern(db, concern_id)
    return {"success": True, "message": f"Concern #{concern_id} deleted."}


@router.post("/reports/{report_id}/verify")
def verify_photo_report(report_id: int, body: VerifyBody, me: CurrentUser = Depends(admin_required),
                        db: Session = Depends(get_db)):
    """An administrator confirms or rejects what the AI found in a photo report."""
    row = db.get(common.MODELS["reports"], report_id)
    if row is None or me.role != "admin" or row.workflow_review != "Accepted" \
            or (row.assigned_admin_email or "").lower() != me.email.lower():
        raise HTTPException(403, "Only the assigned administrator can review this report.")
    photo_report_service.verify(db, me, report_id, body.verification, body.note)
    _log_admin_action(db, me.email, "report_verified", None,
                      f"Report #{report_id} marked {body.verification}.")
    return {"success": True, "message": f"Report #{report_id} marked {body.verification}."}


@router.post("/concerns/{concern_id}/verify")
def verify_photo_concern(concern_id: int, body: VerifyBody, me: CurrentUser = Depends(admin_required),
                         db: Session = Depends(get_db)):
    row = db.get(common.MODELS["concerns"], concern_id)
    if row is None or me.role != "admin" or row.source != "photo" or row.workflow_review != "Accepted" \
            or (row.assigned_admin_email or "").lower() != me.email.lower():
        raise HTTPException(403, "Only the assigned administrator can review this concern.")
    photo_report_service.verify_concern(db, me, concern_id, body.verification, body.note)
    _log_admin_action(db, me.email, "concern_verified", None,
                      f"Concern #{concern_id} marked {body.verification}.")
    return {"success": True, "message": f"Concern #{concern_id} marked {body.verification}."}


# ------------------------------------------------------------- faculty
@router.get("/faculty")
def faculty(_me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    return {"rows": list(reversed(faculty_service.load_records(db)))}


@router.post("/faculty/{record_id}/available")
def faculty_available(record_id: int, me: CurrentUser = Depends(admin_required),
                      db: Session = Depends(get_db)):
    record = faculty_service.get_record(db, record_id)
    if not faculty_service.mark_available_by_id(db, record_id):
        raise ValidationError("Record not found or already available.")
    _log_admin_action(db, me.email, "faculty_availability_changed", record.get("instructor_email"),
                      f"Faculty report #{record_id} marked Available.")
    return {"success": True, "message": "Marked as available."}


class FacultyReviewBody(BaseModel):
    decision: str = ""
    note: str = ""


@router.post("/faculty/{record_id}/review")
def review_faculty(record_id: int, body: FacultyReviewBody,
                   me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    decision = body.decision.strip().title()
    record = faculty_service.get_record(db, record_id)
    if record is None or not faculty_service.review_record(
            db, record_id, me.email, decision, body.note):
        raise ValidationError("This faculty report is no longer awaiting review.")
    _log_admin_action(db, me.email, "faculty_report_" + decision.lower(),
                      record.get("instructor_email"),
                      f"Faculty report #{record_id} {decision.lower()}."
                      + (f" Note: {body.note.strip()[:350]}" if body.note.strip() else ""))
    return {"success": True, "message": f"Faculty report {decision.lower()}."}


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


def _registration_file_bytes(row, binary_column, storage_column):
    key = getattr(row, storage_column, None)
    if key:
        from app.services.private_document_service import read_document
        try:
            data = read_document(key)
        except Exception as exc:
            print("PRIVATE REGISTRATION FILE READ ERROR:", repr(exc)[:200])
            data = None
        if data is None:
            raise HTTPException(502, "The private document store is temporarily unavailable.")
        return data
    return getattr(row, binary_column)


@router.get("/users/{user_id}/verification-document")
def user_verification_document(user_id: int, _me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    row = user_service.get_user(db, user_id)
    if row is None or (not row.verification_document and not row.verification_document_storage_key) or not row.verification_content_type:
        raise HTTPException(404, "Verification document not found.")
    filename = row.verification_filename or "student-verification"
    disposition = "attachment" if row.verification_content_type == "application/pdf" else "inline"
    return Response(_registration_file_bytes(row, "verification_document", "verification_document_storage_key"), media_type=row.verification_content_type,
                    headers={"Content-Disposition": f'{disposition}; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/users/{user_id}/verification-document/cor")
def user_cor_document(user_id: int, _me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    row = user_service.get_user(db, user_id)
    if row is None or (not row.verification_cor_document and not row.verification_cor_storage_key) or not row.verification_cor_content_type:
        raise HTTPException(404, "COR scan not found.")
    filename = row.verification_cor_filename or "student-cor"
    return Response(_registration_file_bytes(row, "verification_cor_document", "verification_cor_storage_key"), media_type=row.verification_cor_content_type,
                    headers={"Content-Disposition": f'inline; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/users/{user_id}/verification-document/id-back")
def user_id_back_document(user_id: int, _me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    row = user_service.get_user(db, user_id)
    if row is None or (not row.verification_id_back_document and not row.verification_id_back_storage_key) or not row.verification_id_back_content_type:
        raise HTTPException(404, "ID back scan not found.")
    filename = row.verification_id_back_filename or "student-id-back"
    return Response(_registration_file_bytes(row, "verification_id_back_document", "verification_id_back_storage_key"), media_type=row.verification_id_back_content_type,
                    headers={"Content-Disposition": f'inline; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/users/{user_id}/face-image")
def user_face_image(user_id: int, _me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    row = user_service.get_user(db, user_id)
    if row is None or (not row.face_image and not row.face_image_storage_key) or not row.face_image_content_type:
        raise HTTPException(404, "Selfie not found.")
    filename = row.face_image_filename or "applicant-selfie.jpg"
    return Response(_registration_file_bytes(row, "face_image", "face_image_storage_key"), media_type=row.face_image_content_type,
                    headers={"Content-Disposition": f'inline; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/users/{user_id}/face-scan-pdf")
def user_face_scan_pdf(user_id: int, _me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    row = user_service.get_user(db, user_id)
    if row is None or (not row.face_scan_pdf and not row.face_scan_pdf_storage_key):
        raise HTTPException(404, "Face scan PDF not found.")
    filename = row.face_scan_pdf_filename or "face-scan.pdf"
    return Response(_registration_file_bytes(row, "face_scan_pdf", "face_scan_pdf_storage_key"), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"',
                             "Cache-Control": "no-store"})


# ------------------------------------- account checks (reports managers)
@router.get("/accounts")
def review_accounts(me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    """First-level check queue: NEMSU and personal-Gmail student/instructor accounts.
    Report managers clear or flag these before the super admin's oversight view."""
    rows = _account_review_rows(db, is_super_admin=me.role == "super_admin")
    return {"rows": rows, "counts": {
        "pending": sum(r["approval_status"] == "Pending"
                        or (r["approval_status"] != "Rejected" and r["review_status"] == "Unreviewed" and r["is_nemsu"]) for r in rows),
        "checked": sum(r["review_status"] == "Checked" for r in rows),
        "flagged": sum(r["review_status"] == "Flagged" for r in rows),
        "rejected": sum(r["approval_status"] == "Rejected" for r in rows),
    }}


def _account_action_refused(message, missing):
    return JSONResponse({"success": False, "message": message, "missing": missing}, status_code=400)


class AccountCheckBody(BaseModel):
    note: str = ""
    flag: bool = False


class AccountRejectBody(BaseModel):
    reason: str = ""


class AccountFaceReviewBody(BaseModel):
    status: str = ""


@router.post("/accounts/{user_id}/approve")
def approve_account(user_id: int, me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    target = user_service.get_user(db, user_id)
    is_super_admin = me.role == "super_admin"
    missing = user_service.account_approval_missing(target, is_super_admin=is_super_admin)
    if target is not None and user_id == me.id:
        missing.append("You cannot approve your own account")
    if missing:
        return _account_action_refused("This account cannot be approved yet.", missing)
    if not user_service.approve_personal_registration(db, user_id, me.email, is_super_admin=is_super_admin):
        return _account_action_refused("This account cannot be approved yet.", ["Account requirements changed. Refresh and review again"])
    _log_admin_action(db, me.email, "account_approved", target.email,
                      f"Approved {target.registration_type} registration.")
    return {"success": True, "message": f"{target.email} approved. The account can sign in now."}


@router.post("/accounts/{user_id}/reject")
def reject_account(user_id: int, body: AccountRejectBody = Body(default=AccountRejectBody()), me: CurrentUser = Depends(admin_required),
                   db: Session = Depends(get_db)):
    target = user_service.get_user(db, user_id)
    if target is None:
        return _account_action_refused("This account could not be rejected.", ["Account not found"])
    if user_id == me.id:
        return _account_action_refused("You cannot reject your own account.", ["You cannot reject your own account"])
    reason = (body.reason or "").strip()
    if len(reason) > 300:
        return _account_action_refused("The rejection reason is too long.", ["Reason must be 300 characters or fewer"])
    if target.approval_status != "Pending" or target.deleted_at:
        return _account_action_refused("This account is not awaiting approval.", ["Account is not pending approval"])
    if not user_service.reject_student_registration(db, user_id, me.email, reason):
        return _account_action_refused("This account is not awaiting approval.", ["Account is not pending approval"])
    _log_admin_action(db, me.email, "account_rejected", target.email,
                      "Rejected personal registration." + (f" Reason: {reason}" if reason else " No reason provided."))
    return {"success": True, "message": f"{target.email} was rejected."}


@router.post("/accounts/{user_id}/check")
def check_review_account(user_id: int, body: AccountCheckBody, me: CurrentUser = Depends(admin_required),
                         db: Session = Depends(get_db)):
    target = user_service.get_user(db, user_id)
    note = (body.note or "").strip()[:500]
    if body.flag and not note:
        return _account_action_refused("Add a note before flagging this account.", ["Flag note is required"])
    if target is None or not user_service.check_account(db, user_id, me.email, body.note, body.flag):
        return _account_action_refused("That account cannot be checked.", ["Account is not eligible for review"])
    detail = note or ("Reported to the super admin." if body.flag
                      else "First-level check complete.")
    _log_admin_action(db, me.email, "account_flagged" if body.flag else "account_checked", target.email, detail)
    return {"success": True,
            "message": (f"{target.email} reported to the super admin." if body.flag
                        else f"{target.email} checked and passed on to the super admin.")}


@router.post("/accounts/{user_id}/face-review")
def review_account_face(user_id: int, body: AccountFaceReviewBody,
                        me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    if body.status not in ("Verified", "Rejected"):
        return _account_action_refused("Choose a valid selfie decision.", ["Choose Verified or Rejected"])
    target = user_service.get_user(db, user_id)
    if (target is None or target.deleted_at or target.approval_status != "Pending"
            or not (target.face_image or target.face_image_storage_key)):
        return _account_action_refused("This account has no pending selfie to review.", ["Pending selfie not found"])
    target.face_review_status = body.status
    db.commit()
    _log_admin_action(db, me.email, "account_selfie_reviewed", target.email,
                      f"Selfie marked {body.status.lower()}.")
    return {"success": True, "message": f"Selfie marked {body.status.lower()}."}


@router.post("/accounts/{user_id}/delete")
def delete_flagged_account(user_id: int, me: CurrentUser = Depends(super_admin_required),
                           db: Session = Depends(get_db)):
    target = user_service.get_user(db, user_id)
    was_rejected = target is not None and target.approval_status == "Rejected"
    if (user_id == me.id or target is None
            or (target.review_status != "Flagged" and target.approval_status != "Rejected")
            or not user_service.soft_delete_user(db, user_id)):
        raise ValidationError("Only a flagged or rejected registration account can be deleted here.")
    description = "Rejected registration account" if was_rejected else "Flagged account"
    _log_admin_action(db, me.email, "account_deleted", target.email,
                      f"{description} disabled by the super admin.")
    db.commit()
    return {"success": True, "message": f"{description} disabled and scheduled for permanent deletion in 7 days."}


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
    review_audit = []
    for row in db.scalars(select(FacultyReport).order_by(FacultyReport.submitted_at.desc()).limit(100)).all():
        review_audit.append({"kind": "Faculty report", "id": row.id, "submitted_at": row.submitted_at,
                             "requester": row.instructor, "handler": row.reviewed_by,
                             "status": row.review_status, "reviewed_at": row.reviewed_at,
                             "note": row.review_note})
    for row in db.scalars(select(Reservation).order_by(Reservation.created_at.desc()).limit(100)).all():
        review_audit.append({"kind": "Reservation", "id": row.id, "submitted_at": row.created_at,
                             "requester": row.requester_name, "handler": row.reviewed_by,
                             "status": row.status, "reviewed_at": row.reviewed_at,
                             "note": row.review_note})
    review_audit.sort(key=lambda item: item["submitted_at"] or datetime.min, reverse=True)
    departments = [{"id": r.id, "name": r.name, "office": r.office}
                   for r in db.scalars(select(CampusDepartment).order_by(CampusDepartment.name)).all()]
    storage = _system_storage(db)
    return {
        "role_counts": [[role, user_service.count_role(db, role)]
                        for role in ("student", "instructor", "admin", "super_admin")],
        "record_counts": [[label, common.count_rows(db, table)] for label, table in (
            ("Reports", "reports"), ("Concerns", "concerns"), ("Reservations", "reservations"),
            ("Feedback", "feedback"))],
        "analytics": chart_service.dashboard_charts(db),
        "ai_providers": systemAi.chain_status(),
        "storage": storage,
        "departments": departments,
        "activity": [{"id": r.id, "actor_email": r.actor_email, "action": r.action,
                      "target_email": r.target_email, "details": r.details,
                      "created_at": r.created_at.strftime("%Y-%m-%d %I:%M:%S %p")} for r in rows],
        "review_audit": [{**r, "submitted_at": r["submitted_at"].strftime("%Y-%m-%d %I:%M:%S %p") if r["submitted_at"] else "",
                          "reviewed_at": r["reviewed_at"].strftime("%Y-%m-%d %I:%M:%S %p") if r["reviewed_at"] else ""}
                         for r in review_audit],
    }


def _system_storage(db: Session):
    """Report local uploads, generated files, database size, and local disk headroom."""
    def folder_size(folder):
        if not folder.exists():
            return 0
        total = 0
        for path in folder.rglob("*"):
            try:
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
            except OSError:
                continue
        return total

    uploads = folder_size(config.UPLOAD_DIR)
    reports = folder_size(config.REPORTS_DIR)
    cloud_storage_configured = all((config.CLOUDINARY_CLOUD_NAME, config.CLOUDINARY_API_KEY,
                                    config.CLOUDINARY_API_SECRET))
    database_bytes = None
    registration_db_file_bytes = None
    registration_file_count = 0
    registration_offloaded_count = 0
    try:
        if db.bind.dialect.name == "postgresql":
            database_bytes = int(db.execute(text(
                "SELECT pg_database_size(current_database())")).scalar_one())
        elif db.bind.dialect.name == "sqlite":
            db_path = db.bind.url.database
            if db_path and db_path != ":memory:":
                from pathlib import Path
                database_bytes = Path(db_path).stat().st_size
        if db.bind.dialect.name in ("postgresql", "sqlite"):
            byte_length = "pg_column_size" if db.bind.dialect.name == "postgresql" else "length"
            private_columns = ("verification_document", "verification_cor_document",
                               "verification_id_back_document", "face_image", "face_scan_pdf")
            sizes = " + ".join(f"COALESCE({byte_length}({name}), 0)" for name in private_columns)
            key_columns = ("verification_document_storage_key", "verification_cor_storage_key",
                           "verification_id_back_storage_key", "face_image_storage_key",
                           "face_scan_pdf_storage_key")
            count_expr = " + ".join(f"CASE WHEN {name} IS NOT NULL THEN 1 ELSE 0 END" for name in key_columns)
            totals = db.execute(text(
                f"SELECT COALESCE(SUM({sizes}),0), COALESCE(SUM({count_expr}),0) FROM users"
            )).one()
            registration_db_file_bytes = int(totals[0] or 0)
            registration_offloaded_count = int(totals[1] or 0)
            registration_file_count = int(db.execute(text(
                "SELECT COALESCE(SUM(" + " + ".join(
                    f"CASE WHEN {name} IS NOT NULL OR {blob} IS NOT NULL THEN 1 ELSE 0 END"
                    for name, blob in zip(key_columns, private_columns)) + "),0) FROM users"
            )).scalar_one())
    except Exception:
        database_bytes = None
    try:
        disk = shutil.disk_usage(config.UPLOAD_DIR if config.UPLOAD_DIR.exists() else config.BACKEND_DIR)
        disk_total, disk_used, disk_free = disk.total, disk.used, disk.free
    except OSError:
        disk_total = disk_used = disk_free = None
    return {
        "uploads_bytes": uploads,
        "generated_files_bytes": reports,
        "database_bytes": database_bytes,
        "registration_database_file_bytes": registration_db_file_bytes,
        "registration_file_count": registration_file_count,
        "registration_offloaded_file_count": registration_offloaded_count,
        "disk_total_bytes": disk_total,
        "disk_used_bytes": disk_used,
        "disk_free_bytes": disk_free,
        "cloud_storage_configured": cloud_storage_configured,
        "cloud_storage_note": ("New registration evidence and report photos use private Cloudinary storage. Older registration files stay in Neon until migrated and purged; remote usage is not included in local disk totals." if cloud_storage_configured else "Cloudinary is not configured. Registration evidence currently uses database storage; configure Cloudinary and REGISTRATION_STORAGE_REQUIRED=true to prevent new files from using Neon."),
    }


@router.get("/system/admins")
def system_admin_accounts(_me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.role.in_(("admin", "super_admin")))
                      .order_by(User.role, User.name)).all()
    return {"rows": [{"id": row.id, "name": row.name, "email": row.email,
                       "department": row.department, "role": row.role,
                       "is_allowlisted_admin": is_admin_email(row.email),
                       "deleted_at": row.deleted_at, "is_active": row.is_active,
                       "approval_status": row.approval_status} for row in rows]}


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
ROOM_FIELDS = [["room_id", "Room ID", True], ["name", "Name", True],
               ["building", "Building", False, "select", []],
               ["department", "Department", False, "select", []],
               ["room_type", "Type", False, "select", ["Classroom", "Computer Laboratory", "Laboratory", "Lecture Hall", "Office", "Conference Room", "Other"]],
               ["capacity", "Capacity", False, "select", ["1-10", "11-20", "21-30", "31-40", "40-50", "51-100", "100+" ]],
               ["equipment", "Equipment", False, "multiselect", ["Projector", "Computers", "TV Screen", "Air Conditioning", "Whiteboard", "Sound System", "None", "Other"]],
               ["status", "Availability", False, "select", ["Available", "In Use", "Under Maintenance", "Not Available"]]]
CAMPUS_FIELDS = [["topic", "Topic", True], ["keywords", "Keywords (use ; between them)", True],
                 ["answer", "Answer", True]]


@router.get("/rooms")
def rooms(page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=250),
          search: str = "", department: str = "",
          _me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    rows, total = room_service.list_rooms_page(db, page, page_size, search[:120], department[:120])
    fields = [field.copy() for field in ROOM_FIELDS]
    building_options = room_service.list_building_options(db)
    department_options = room_service.list_department_options(db)
    if "Other" not in {option["value"] for option in department_options}:
        department_options.append({"value": "Other", "label": "Other"})
    next(field for field in fields if field[0] == "building")[4] = building_options
    next(field for field in fields if field[0] == "department")[4] = department_options
    return {"title": "Rooms", "fields": fields, "rows": rows,
            "pagination": {"page": page, "page_size": page_size, "total": total,
                           "pages": max(1, (total + page_size - 1) // page_size)},
            "department_options": department_options,
            "building_options": building_options,
            "empty": "No rooms yet. Add the real rooms so the AI never has to guess."}


@router.post("/rooms")
def rooms_add(body: dict, _me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    room_service.add_room(db, _strings(body))
    return {"success": True, "message": "Room added."}


@router.post("/rooms/import")
async def rooms_import(file: UploadFile = File(...), _me: CurrentUser = Depends(super_admin_required),
                       db: Session = Depends(get_db)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise ValidationError("Choose a CSV file.")
    raw = await file.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        raise ValidationError("The CSV file must be 20 MB or smaller.")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if not reader.fieldnames:
            raise ValidationError("The CSV must include a header row.")
        headers = {header.strip().lower().replace(" ", "_"): header for header in reader.fieldnames if header}
        required = {"room_id", "name"}
        if not required.issubset(headers):
            raise ValidationError("CSV must include room_id and name columns.")
        records = []
        for row in reader:
            records.append({key: row.get(original) for key, original in headers.items()})
            if len(records) > 25000:
                raise ValidationError("Import no more than 25,000 rooms at a time.")
        imported = room_service.import_rooms(db, records)
    except UnicodeDecodeError as exc:
        raise ValidationError("The CSV must use UTF-8 encoding.") from exc
    except csv.Error as exc:
        raise ValidationError("The CSV format could not be read.") from exc
    return {"success": True, "message": f"Imported {imported} room rows."}


@router.put("/rooms/{row_id}")
def rooms_update(row_id: int, body: dict, _me: CurrentUser = Depends(super_admin_required), db: Session = Depends(get_db)):
    room_service.update_room(db, row_id, _strings(body))
    return {"success": True, "message": "Room updated."}


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
def announcements_add(body: dict, me: CurrentUser = Depends(admin_required), db: Session = Depends(get_db)):
    announcement_service.add_announcement(db, _strings(body), me.name, me.role)
    return {"success": True, "message": "Announcement posted."}


@router.delete("/announcements/{row_id}")
def announcements_delete(row_id: int, db: Session = Depends(get_db)):
    announcement_service.delete_announcement(db, row_id)
    return {"success": True, "message": "Announcement deleted."}
