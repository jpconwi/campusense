"""services/concern_service.py - facility / equipment concerns."""

from sqlalchemy.orm import Session

from app import config
from app.models import Concern
from app.services import common
from app.services.common import clean_choice, clean_date, clean_text, now
from app.services.pdf_service import generate_pdf
from app.services.upload_service import save_image

CONCERN_TYPES = ["Equipment", "Electrical", "Plumbing", "Furniture",
                 "Building / Structure", "Cleanliness", "Safety", "Other"]


def pdf_path(concern_id):
    return config.REPORTS_DIR / "concerns" / f"concern_{int(concern_id):04d}.pdf"


def create_concern(db: Session, user, form, image_file):
    """Name and email always come from the logged-in account."""
    location = clean_text(form.get("location"), "Location / Area", 120)
    room = clean_text(form.get("room"), "Room", 60, required=False)
    concern_type = clean_choice(form.get("concern_type"), "Concern type", CONCERN_TYPES)
    description = clean_text(form.get("description"), "Description", 2000)
    concern_date = clean_date(form.get("concern_date"), "Date", allow_future=False)
    image = save_image(image_file)

    stamp = now()
    row = Concern(user_id=user.id, reporter_name=user.name, reporter_email=user.email,
                  location=location, room=room, concern_type=concern_type,
                  description=description, concern_date=concern_date, image_filename=image,
                  status="Pending", created_at=stamp, updated_at=stamp)
    db.add(row)
    db.commit()

    generate_pdf(pdf_path(row.id), "Campus Concern Report", [
        ("Concern ID", row.id), ("Name", user.name), ("Email", user.email),
        ("Location", location), ("Room", room or "-"), ("Concern Type", concern_type),
        ("Description", description), ("Date", concern_date.isoformat()),
        ("Submitted At", stamp.strftime("%Y-%m-%d %H:%M:%S")), ("Status", "Pending"),
    ])
    return common.get_row(db, "concerns", row.id)
