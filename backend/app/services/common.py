"""
services/common.py - helpers shared by the concern/report/feedback/
reservation services: statuses, validation, and generic queries.
"""

import re
from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Concern, Feedback, Report, Reservation, User

# ------------------------------------------------------------ statuses
WORKFLOW_STATUSES = ["Pending", "Under Review", "In Progress", "Resolved", "Rejected"]
FEEDBACK_STATUSES = ["Pending", "Reviewed"]
RESERVATION_STATUSES = ["Pending", "Approved", "Rejected", "Cancelled"]

TABLE_STATUSES = {
    "concerns": WORKFLOW_STATUSES,
    "reports": WORKFLOW_STATUSES,
    "feedback": FEEDBACK_STATUSES,
    "reservations": RESERVATION_STATUSES,
}

# Fixed table names -> models (SQL is never built from user input)
MODELS = {"concerns": Concern, "reports": Report, "feedback": Feedback, "reservations": Reservation}

# Columns shown in tables: (header, key, private)
# private=True means only admins see the column.
COLUMNS = {
    "concerns": [
        ("ID", "id", False), ("Submitted", "created_at", False),
        ("Name", "reporter_name", True), ("Email", "reporter_email", True),
        ("From", "submitter_role", True),
        ("Type", "concern_type", False), ("Location", "location", False),
        ("Room", "room", False), ("Description", "description", False),
        ("Status", "status", False),
    ],
    "reports": [
        ("ID", "id", False), ("Submitted", "created_at", False),
        ("Reporter", "reporter_name", True), ("Email", "reporter_email", True),
        ("From", "submitter_role", True),
        ("Type", "report_type", False), ("Location", "location", False),
        ("Area", "area", False), ("Room", "room", False),
        ("Description", "description", False), ("Status", "status", False),
    ],
    "feedback": [
        ("ID", "id", False), ("Submitted", "created_at", False),
        ("Name", "name", True), ("Email", "email", True),
        ("From", "submitter_role", True),
        ("Area", "area", False), ("Type", "feedback_type", False),
        ("Message", "message", False), ("Status", "status", False),
    ],
    "reservations": [
        ("ID", "id", False), ("Submitted", "created_at", False),
        ("Requester", "requester_name", True), ("Email", "requester_email", True),
        ("From", "submitter_role", True),
        ("Facility", "facility", False), ("Purpose", "purpose", False),
        ("Date", "reservation_date", False), ("Time", "time_range", False),
        ("Additional info", "additional_info", False), ("Status", "status", False),
    ],
}


class ValidationError(Exception):
    """Raised with a message that is safe to show to the user."""


# ---------------------------------------------------------- validation
def now():
    return datetime.now().replace(microsecond=0)


def now_str():
    return now().strftime("%Y-%m-%d %H:%M:%S")


def clean_text(value, label, max_len=200, required=True):
    value = (value or "").strip()
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)  # control chars
    if required and not value:
        raise ValidationError(f"{label} is required.")
    if len(value) > max_len:
        raise ValidationError(f"{label} must be {max_len} characters or fewer.")
    return value


def clean_choice(value, label, options):
    value = (value or "").strip()
    if value not in options:
        raise ValidationError(f"Please choose a valid {label.lower()}.")
    return value


def clean_date(value, label, allow_future=True, allow_past=True):
    """Returns a datetime.date."""
    value = (value or "").strip()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"{label} must be a valid date.")
    today = datetime.now().date()
    if not allow_future and parsed > today:
        raise ValidationError(f"{label} cannot be in the future.")
    if not allow_past and parsed < today:
        raise ValidationError(f"{label} cannot be in the past.")
    return parsed


def clean_time(value, label):
    """Returns a datetime.time."""
    value = (value or "").strip()
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        raise ValidationError(f"{label} must be a valid time.")


# ------------------------------------------------------- serialisation
def row_to_dict(obj):
    """ORM row -> plain dict. Dates/times become the same text the old app used."""
    data = {}
    for column in obj.__table__.columns:
        value = getattr(obj, column.key)
        if isinstance(value, datetime):
            value = value.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(value, date):
            value = value.strftime("%Y-%m-%d")
        elif isinstance(value, time):
            value = value.strftime("%H:%M")
        data[column.key] = value
    return data


def _add_extras(data):
    if "start_time" in data:
        data["time_range"] = f'{data["start_time"]} - {data["end_time"]}'
    return data


# ------------------------------------------------------ generic queries
def _model(table):
    if table not in MODELS:
        raise ValueError("Unknown table")
    return MODELS[table]


def list_rows(db: Session, table, user_id=None, status=None, limit=None):
    """Newest first. Optional filter by owner and/or status."""
    model = _model(table)
    query = select(model, User.role).outerjoin(User, User.id == model.user_id)
    if user_id is not None:
        query = query.where(model.user_id == user_id)
    if status:
        query = query.where(model.status == status)
    query = query.order_by(model.id.desc())
    if limit:
        query = query.limit(int(limit))
    rows = []
    for obj, role in db.execute(query).all():
        data = row_to_dict(obj)
        data["submitter_role"] = role
        rows.append(_add_extras(data))
    return rows


def get_row(db: Session, table, row_id):
    obj = db.get(_model(table), row_id)
    return _add_extras(row_to_dict(obj)) if obj else None


def count_rows(db: Session, table, status=None, user_id=None):
    model = _model(table)
    query = select(func.count()).select_from(model)
    if status:
        query = query.where(model.status == status)
    if user_id is not None:
        query = query.where(model.user_id == user_id)
    return db.execute(query).scalar_one()


def update_status(db: Session, table, row_id, status):
    model = _model(table)
    if status not in TABLE_STATUSES[table]:
        raise ValidationError("Invalid status.")
    obj = db.get(model, row_id)
    if obj is None:
        return False
    obj.status = status
    obj.updated_at = now()
    db.commit()
    return True
