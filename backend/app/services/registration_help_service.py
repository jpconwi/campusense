"""Contact inbox for applicants who cannot finish account registration."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RegistrationHelpMessage
from app.services.common import ValidationError, now


def create_message(db: Session, name, email, applicant_type, message):
    name = re.sub(r"[\x00-\x1f\x7f]", " ", (name or "")).strip()[:120]
    email = (email or "").strip().lower()[:255]
    applicant_type = (applicant_type or "").strip().lower()
    message = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", (message or "")).strip()
    if len(name) < 2:
        raise ValidationError("Enter your name.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValidationError("Enter a valid email address so the admin can reply.")
    if applicant_type not in ("student", "instructor"):
        raise ValidationError("Choose student or instructor.")
    if not message or len(message) > 2000:
        raise ValidationError("Write a message of up to 2,000 characters.")
    row = RegistrationHelpMessage(name=name, email=email, applicant_type=applicant_type,
                                  message=message, status="New", created_at=now())
    db.add(row)
    db.commit()
    return row


def list_messages(db: Session):
    rows = db.execute(select(RegistrationHelpMessage).order_by(
        RegistrationHelpMessage.created_at.desc(), RegistrationHelpMessage.id.desc())).scalars()
    return [{"id": row.id, "name": row.name, "email": row.email,
             "applicant_type": row.applicant_type, "message": row.message,
             "status": row.status, "created_at": row.created_at.isoformat(),
             "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None}
            for row in rows]


def resolve_message(db: Session, message_id):
    row = db.get(RegistrationHelpMessage, message_id)
    if row is None or row.status == "Resolved":
        return False
    row.status = "Resolved"
    row.resolved_at = now()
    db.commit()
    return True
