"""
services/reservation_service.py - facility / room reservation requests.

A new request is ALWAYS "Pending". Only an admin can approve it, and the
backend refuses to approve a time that overlaps another Approved reservation.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Reservation
from app.services import common
from app.services.common import (ValidationError, clean_date, clean_text,
                                 clean_time, now, row_to_dict)


def find_conflict(db: Session, facility, date, start, end, exclude_id=None):
    row = db.execute(
        select(Reservation).where(
            func.lower(Reservation.facility) == facility.lower(),
            Reservation.reservation_date == date,
            Reservation.status == "Approved",
            Reservation.start_time < end,
            Reservation.end_time > start,
            Reservation.id != (exclude_id or 0),
        ).limit(1)
    ).scalar_one_or_none()
    return row_to_dict(row) if row else None


def create_reservation(db: Session, user, form):
    facility = clean_text(form.get("facility"), "Facility / Room", 120)
    purpose = clean_text(form.get("purpose"), "Purpose", 300)
    date = clean_date(form.get("reservation_date"), "Date", allow_past=False)
    start = clean_time(form.get("start_time"), "Start time")
    end = clean_time(form.get("end_time"), "End time")
    info = clean_text(form.get("additional_info"), "Additional information", 1000, required=False)

    if end <= start:
        raise ValidationError("End time must be after the start time.")

    conflict = find_conflict(db, facility, date, start, end)
    if conflict:
        raise ValidationError(
            f"{facility} is already reserved on {date.isoformat()} from "
            f"{conflict['start_time']} to {conflict['end_time']}. Please choose another time."
        )

    stamp = now()
    row = Reservation(user_id=user.id, requester_name=user.name, requester_email=user.email,
                      facility=facility, purpose=purpose, reservation_date=date,
                      start_time=start, end_time=end, additional_info=info,
                      status="Pending", created_at=stamp, updated_at=stamp)
    db.add(row)
    db.commit()
    return common.get_row(db, "reservations", row.id)


def change_status(db: Session, reservation_id, status):
    """Admin only. Checks for overlaps before approving."""
    row = db.get(Reservation, reservation_id)
    if row is None:
        raise ValidationError("Reservation not found.")
    if status == "Approved":
        conflict = find_conflict(db, row.facility, row.reservation_date,
                                 row.start_time, row.end_time, exclude_id=row.id)
        if conflict:
            raise ValidationError("Cannot approve: that time overlaps reservation "
                                  f"#{conflict['id']} which is already approved.")
    common.update_status(db, "reservations", reservation_id, status)
