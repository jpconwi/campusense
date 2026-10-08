"""
routers/admin.py - the Admin Dashboard API (/api/admin/...).

Every route here needs the admin role. The role is checked on the server
from the database + ADMIN_EMAILS list, never from the browser. Anyone who is
not a signed-in admin gets a plain 404.
All numbers on the dashboard are real counts from the database.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import (CurrentUser, admin_required, csrf_protect, is_admin_email)
from app.services import (announcement_service, campus_service, chart_service, common, faculty_service,
                          reservation_service, room_service, user_service)
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
        ["Resolved Reports", common.count_rows(db, "reports", "Resolved")],
        ["Faculty Reports", len(faculty)],
        ["Total Feedback", common.count_rows(db, "feedback")],
        ["Total Reservations", common.count_rows(db, "reservations")],
    ]
    return {
        "stats": stats,
        "charts": chart_service.dashboard_charts(db),
        "recent_concerns": common.list_rows(db, "concerns", status="Pending", limit=5),
        "recent_reports": common.list_rows(db, "reports", status="Pending", limit=5),
    }


# -------------------------------------------------------- record lists
@router.get("/records/{kind}")
def records(kind: str, status: Optional[str] = None, db: Session = Depends(get_db)):
    if kind not in SECTIONS:
        raise HTTPException(404, "That page was not found.")
    if status and status not in common.TABLE_STATUSES[kind]:
        status = None
    return {
        "kind": kind, "spec": SECTIONS[kind], "current": status,
        "statuses": common.TABLE_STATUSES[kind],
        "columns": [[h, k] for h, k, _ in common.COLUMNS[kind]],
        "rows": common.list_rows(db, kind, status=status),
    }


class StatusBody(BaseModel):
    status: str = ""


@router.post("/records/{kind}/{row_id}/status")
def change_status(kind: str, row_id: int, body: StatusBody, db: Session = Depends(get_db)):
    if kind not in SECTIONS:
        raise HTTPException(404, "That page was not found.")
    if kind == "reservations":
        reservation_service.change_status(db, row_id, body.status)
    elif not common.update_status(db, kind, row_id, body.status):
        raise ValidationError("Record not found.")
    return {"success": True, "message": f"Status of #{row_id} changed to {body.status}."}


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
def users(db: Session = Depends(get_db)):
    rows = user_service.list_users(db)
    for r in rows:
        r.pop("google_id", None)                 # not needed by the browser
        r["is_allowlisted_admin"] = is_admin_email(r["email"])
    return {"rows": rows}


class RoleBody(BaseModel):
    role: str = ""


class ActiveBody(BaseModel):
    active: bool = True


@router.post("/users/{user_id}/role")
def user_role(user_id: int, body: RoleBody, me: CurrentUser = Depends(admin_required),
              db: Session = Depends(get_db)):
    if user_id == me.id:
        raise ValidationError("You cannot change your own role.")
    if not user_service.admin_set_role(db, user_id, body.role):
        raise ValidationError("Could not change that role (admins are set in ADMIN_EMAILS).")
    return {"success": True, "message": "Role updated."}


@router.post("/users/{user_id}/active")
def user_active(user_id: int, body: ActiveBody, me: CurrentUser = Depends(admin_required),
                db: Session = Depends(get_db)):
    if user_id == me.id:
        raise ValidationError("You cannot deactivate yourself.")
    if not user_service.set_active(db, user_id, body.active):
        raise ValidationError("Could not change that account.")
    return {"success": True,
            "message": "Account activated." if body.active else "Account deactivated."}


# ------------------------------------------------------ rooms / campus
ROOM_FIELDS = [["room_id", "Room ID", True], ["name", "Name", True], ["building", "Building", False],
               ["room_type", "Type", False], ["capacity", "Capacity", False],
               ["equipment", "Equipment", False], ["status", "Status", False]]
CAMPUS_FIELDS = [["topic", "Topic", True], ["keywords", "Keywords (use ; between them)", True],
                 ["answer", "Answer", True]]


@router.get("/rooms")
def rooms(db: Session = Depends(get_db)):
    return {"title": "Rooms", "fields": ROOM_FIELDS, "rows": room_service.list_rooms(db),
            "empty": "No rooms yet. Add the real rooms so the AI never has to guess."}


@router.post("/rooms")
def rooms_add(body: dict, db: Session = Depends(get_db)):
    room_service.add_room(db, _strings(body))
    return {"success": True, "message": "Room added."}


@router.delete("/rooms/{row_id}")
def rooms_delete(row_id: int, db: Session = Depends(get_db)):
    room_service.delete_room(db, row_id)
    return {"success": True, "message": "Room deleted."}


@router.get("/campus")
def campus(db: Session = Depends(get_db)):
    return {"title": "Campus Information", "fields": CAMPUS_FIELDS,
            "rows": campus_service.list_info(db), "empty": "No campus information yet."}


@router.post("/campus")
def campus_add(body: dict, db: Session = Depends(get_db)):
    campus_service.add_info(db, _strings(body))
    return {"success": True, "message": "Campus information added."}


@router.delete("/campus/{row_id}")
def campus_delete(row_id: int, db: Session = Depends(get_db)):
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
