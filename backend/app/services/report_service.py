"""services/report_service.py - campus reports."""

from sqlalchemy.orm import Session

from app import config
from app.models import Report
from app.services import common
from app.services.common import clean_choice_other, clean_date, clean_text, now
from app.services import sentiment_service
from app.services.pdf_service import generate_pdf
from app.services.upload_service import delete_image, save_image

REPORT_TYPES = ["Maintenance", "Safety", "Security", "Cleanliness",
                "Equipment", "Lost & Found", "Other"]


def pdf_path(report_id):
    return config.REPORTS_DIR / "reports" / f"report_{int(report_id):04d}.pdf"


def create_report(db: Session, user, form, image_file):
    location = clean_text(form.get("location"), "Location", 120)
    area = clean_text(form.get("area"), "Area", 120, required=False)
    room = clean_text(form.get("room"), "Room", 60, required=False)
    report_type = clean_choice_other(form, "report_type", "Report type", REPORT_TYPES)
    description = clean_text(form.get("description"), "Description", 2000)
    report_date = clean_date(form.get("report_date"), "Date", allow_future=False)
    image = save_image(image_file)

    mood = sentiment_service.analyze(description)
    stamp = now()
    row = Report(user_id=user.id, reporter_name=user.name, reporter_email=user.email,
                 location=location, area=area, room=room, report_type=report_type,
                 description=description, report_date=report_date, image_filename=image,
                 status="Pending", sentiment=mood["label"], sentiment_score=mood["score"],
                 assigned_admin_email=common.assigned_report_admin(report_type),
                 created_at=stamp, updated_at=stamp)
    db.add(row)
    db.commit()

    generate_pdf(pdf_path(row.id), "Campus Report", [
        ("Report ID", row.id), ("Reporter", user.name), ("Email", user.email),
        ("Location", location), ("Area", area or "-"), ("Room", room or "-"),
        ("Report Type", report_type), ("Description", description),
        ("Date", report_date.isoformat()),
        ("Submitted At", stamp.strftime("%Y-%m-%d %H:%M:%S")), ("Status", "Pending"),
    ])
    return common.get_row(db, "reports", row.id)


def delete_report(db: Session, report_id):
    """Permanently delete a report and its generated files (admin action)."""
    row = db.get(Report, report_id)
    if row is None:
        raise common.ValidationError("Report not found.")
    image_filename = row.image_filename
    generated_pdf = pdf_path(report_id)
    db.delete(row)
    db.commit()
    delete_image(image_filename)
    try:
        generated_pdf.unlink(missing_ok=True)
    except OSError:
        pass
