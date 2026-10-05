"""services/feedback_service.py - feedback about campus areas/facilities."""

from sqlalchemy.orm import Session

from app import config
from app.models import Feedback
from app.services import common
from app.services.common import clean_choice, clean_date, clean_text, now
from app.services.pdf_service import generate_pdf

FEEDBACK_TYPES = ["Compliment", "Suggestion", "Complaint", "Other"]


def pdf_path(feedback_id):
    return config.REPORTS_DIR / "feedback" / f"feedback_{int(feedback_id):04d}.pdf"


def create_feedback(db: Session, user, form):
    area = clean_text(form.get("area"), "Area / Facility", 120)
    feedback_type = clean_choice(form.get("feedback_type"), "Feedback type", FEEDBACK_TYPES)
    message = clean_text(form.get("message"), "Message", 2000)
    feedback_date = clean_date(form.get("feedback_date"), "Date", allow_future=False)

    stamp = now()
    row = Feedback(user_id=user.id, name=user.name, email=user.email, area=area,
                   feedback_type=feedback_type, message=message, feedback_date=feedback_date,
                   status="Pending", created_at=stamp, updated_at=stamp)
    db.add(row)
    db.commit()

    generate_pdf(pdf_path(row.id), "Campus Feedback", [
        ("Feedback ID", row.id), ("Name", user.name), ("Email", user.email),
        ("Area / Facility", area), ("Feedback Type", feedback_type),
        ("Message", message), ("Date", feedback_date.isoformat()),
        ("Submitted At", stamp.strftime("%Y-%m-%d %H:%M:%S")), ("Status", "Pending"),
    ])
    return common.get_row(db, "feedback", row.id)
