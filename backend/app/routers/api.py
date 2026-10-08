"""routers/api.py - JSON endpoints used by the chat window, the forms and the list pages."""

import re
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.ai.ai_engine import ask_ai
from app.database import get_db
from app.security import CurrentUser, csrf_protect, login_required, role_required
from app.services import (announcement_service, common, concern_service, faculty_service, feedback_service,
                          pdf_service, report_service, reservation_service)

router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(csrf_protect)])

USER_KINDS = {
    "concerns": {"title": "My Concerns", "form": "concern", "image": True,
                 "intro": "Report broken equipment or facility problems. You can follow the status here."},
    "reports": {"title": "My Reports", "form": "report", "image": True,
                "intro": "Submit campus reports and follow their status."},
    "feedback": {"title": "Feedback", "form": "feedback", "image": False,
                 "intro": "Tell us what you think about a campus area or facility."},
    "reservations": {"title": "Reservations", "form": "reservation", "image": False,
                     "intro": "Request a room or facility. A request stays Pending until an administrator approves it."},
}
PDF_KINDS = ("concerns", "reports", "feedback")

# very small rate limit so nobody can drain the AI quota: 20 questions / minute
_recent = defaultdict(deque)


def _too_many(user_id, limit=20, window=60):
    now = time.time()
    q = _recent[user_id]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    return False


def _ok(row, message, pdf_kind=None):
    data = {"success": True, "message": message, "id": row["id"], "status": row["status"],
            "submitted_at": row.get("created_at", row.get("submitted_at"))}
    if pdf_kind:
        data["pdf_url"] = f"/api/pdf/{pdf_kind}/{row['id']}"
    return data


# ------------------------------------------------------------------- chat
class AskBody(BaseModel):
    question: str = ""


@router.post("/ask")
def ask(body: AskBody, user: CurrentUser = Depends(login_required), db: Session = Depends(get_db)):
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Question is required.")
    if _too_many(user.id):
        raise HTTPException(429, "Please wait a moment before asking again.")
    try:
        return ask_ai(db, question, user)
    except Exception as error:               # never leak details to the browser
        print("AI ERROR:", repr(error))
        raise HTTPException(500, "Something went wrong. Please try again.")


# ------------------------------------------------------------------ forms
@router.post("/concerns")
def submit_concern(
        location: str = Form(""), room: str = Form(""), concern_type: str = Form(""),
        description: str = Form(""), concern_date: str = Form(""),
        image: Optional[UploadFile] = File(None),
        user: CurrentUser = Depends(role_required("student", "instructor")),
        db: Session = Depends(get_db)):
    form = {"location": location, "room": room, "concern_type": concern_type,
            "description": description, "concern_date": concern_date}
    row = concern_service.create_concern(db, user, form, image)
    return _ok(row, "Your concern has been submitted. Its status is Pending.", "concerns")


@router.post("/reports")
def submit_report(
        location: str = Form(""), area: str = Form(""), room: str = Form(""),
        report_type: str = Form(""), description: str = Form(""), report_date: str = Form(""),
        image: Optional[UploadFile] = File(None),
        user: CurrentUser = Depends(role_required("student", "instructor")),
        db: Session = Depends(get_db)):
    form = {"location": location, "area": area, "room": room, "report_type": report_type,
            "description": description, "report_date": report_date}
    row = report_service.create_report(db, user, form, image)
    return _ok(row, "Your report has been submitted. Its status is Pending.", "reports")


@router.post("/feedback")
def submit_feedback(
        area: str = Form(""), feedback_type: str = Form(""), message: str = Form(""),
        feedback_date: str = Form(""),
        user: CurrentUser = Depends(role_required("student", "instructor")),
        db: Session = Depends(get_db)):
    form = {"area": area, "feedback_type": feedback_type, "message": message,
            "feedback_date": feedback_date}
    row = feedback_service.create_feedback(db, user, form)
    return _ok(row, "Thank you! Your feedback has been submitted.", "feedback")


@router.post("/reservations")
def submit_reservation(
        facility: str = Form(""), purpose: str = Form(""), reservation_date: str = Form(""),
        start_time: str = Form(""), end_time: str = Form(""), additional_info: str = Form(""),
        user: CurrentUser = Depends(role_required("student", "instructor")),
        db: Session = Depends(get_db)):
    form = {"facility": facility, "purpose": purpose, "reservation_date": reservation_date,
            "start_time": start_time, "end_time": end_time, "additional_info": additional_info}
    row = reservation_service.create_reservation(db, user, form)
    return _ok(row, "Your reservation request was sent. It is Pending until an "
                    "administrator approves it.")


# ---------------------------------------------------------------- faculty
@router.post("/faculty/submit")
def submit_faculty(
        reason: str = Form(""), start_date: str = Form(""), expected_return: str = Form(""),
        user: CurrentUser = Depends(role_required("instructor")),
        db: Session = Depends(get_db)):
    form = {"reason": reason, "start_date": start_date, "expected_return": expected_return}
    row = faculty_service.create_faculty_report(db, user, form)
    return {
        "success": True,
        "message": "Your faculty availability report has been submitted successfully.",
        "id": row["display_id"], "instructor": row["instructor"], "status": row["status"],
        "submitted_at": row["submitted_at"], "expected_return": row["expected_return"],
        "pdf_url": f"/api/pdf/faculty/{row['id']}",
    }


@router.post("/faculty/available")
def mark_available(user: CurrentUser = Depends(role_required("instructor")),
                   db: Session = Depends(get_db)):
    changed = faculty_service.mark_available_for_email(db, user.email)
    return {"success": True, "changed": changed}


@router.get("/faculty/check")
def check_faculty(name: str = "", user: CurrentUser = Depends(login_required),
                  db: Session = Depends(get_db)):
    """Kept from the original app. Reads the table, never asks the AI."""
    name = name.strip()
    if not name:
        raise HTTPException(400, "Instructor name is required.")
    records = faculty_service.find_current_records(db, name)
    if not records:
        return {"available": None, "message": f"I don't have an availability record for {name}."}
    row = records[0]
    absent = (row["status"] or "").lower() == "absent"
    return {
        "available": not absent, "instructor": row["instructor"],
        "expected_return": row["expected_return"] if absent else None,
        "message": faculty_service.availability_reply(db, name),
    }


# ------------------------------------------- pages for students/instructors
@router.get("/home")
def home(user: CurrentUser = Depends(login_required), db: Session = Depends(get_db)):
    return {"counts": {k: common.count_rows(db, k, status="Pending", user_id=user.id)
                       for k in USER_KINDS}}


@router.get("/me/records/{kind}")
def my_records(kind: str, user: CurrentUser = Depends(role_required("student", "instructor")),
               db: Session = Depends(get_db)):
    if kind not in USER_KINDS:
        raise HTTPException(404, "That page was not found.")
    return {
        "kind": kind, "spec": USER_KINDS[kind], "pdf": kind in PDF_KINDS,
        "rows": common.list_rows(db, kind, user_id=user.id),
        "columns": [[h, k] for h, k, private in common.COLUMNS[kind] if not private],
    }


@router.get("/me/faculty")
def my_faculty(user: CurrentUser = Depends(role_required("instructor")),
               db: Session = Depends(get_db)):
    return {"rows": faculty_service.records_for_email(db, user.email)}


@router.get("/announcements")
def active_announcements(user: CurrentUser = Depends(login_required),
                         db: Session = Depends(get_db)):
    """Current announcements for every signed-in user (web and mobile app)."""
    return {"rows": [{k: r[k] for k in ("id", "title", "category", "body", "start_date",
                                         "end_date")}
                     for r in announcement_service.list_active(db)]}


# ------------------------------------------------------------------ files
def _owns_faculty_record(user, record):
    if user.is_admin:
        return True
    if record["instructor_email"]:
        return record["instructor_email"] == user.email.lower()
    return faculty_service.normalize_text(record["instructor"]) == \
        faculty_service.normalize_text(user.name)


@router.get("/pdf/{kind}/{record_id}")
def pdf(kind: str, record_id: str, user: CurrentUser = Depends(login_required),
        db: Session = Depends(get_db)):
    """Only the owner (or an admin) can download a PDF."""
    if not record_id.isdigit():
        raise HTTPException(404, "That page was not found.")
    rid = int(record_id)
    if kind == "faculty":
        record = faculty_service.get_record(db, rid)
        if record is None or not _owns_faculty_record(user, record):
            raise HTTPException(404, "That page was not found.")
        path = faculty_service.pdf_path(record["id"])
        pdf_service.ensure_pdf("faculty", record, path)
    else:
        builders = {"concerns": concern_service.pdf_path,
                    "reports": report_service.pdf_path,
                    "feedback": feedback_service.pdf_path}
        if kind not in builders:
            raise HTTPException(404, "That page was not found.")
        row = common.get_row(db, kind, rid)
        if row is None or (not user.is_admin and row["user_id"] != user.id):
            raise HTTPException(404, "That page was not found.")
        path = builders[kind](row["id"])
        pdf_service.ensure_pdf(kind, row, path)
    return FileResponse(path, media_type="application/pdf")


_IMAGE_NAME = re.compile(r"^[a-f0-9]{32}\.(png|jpg|webp)$")


@router.get("/uploads/{filename}")
def upload(filename: str, user: CurrentUser = Depends(login_required),
           db: Session = Depends(get_db)):
    """Uploaded images are private: owner or admin only."""
    if _IMAGE_NAME.match(filename):
        for table in ("concerns", "reports"):
            model = common.MODELS[table]
            owner_id = db.execute(select(model.user_id).where(
                model.image_filename == filename).limit(1)).scalar_one_or_none()
            if owner_id is not None:
                image_path = config.UPLOAD_DIR / filename
                if (user.is_admin or owner_id == user.id) and image_path.exists():
                    return FileResponse(image_path)
                break
    raise HTTPException(404, "That page was not found.")
