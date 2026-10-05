"""
services/room_service.py - room information (rooms table).

The table is empty at first. Admins add the real rooms from the dashboard,
so the AI never has to guess room details.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Room
from app.services.common import ValidationError, clean_text, row_to_dict

FIELDS = ["room_id", "name", "building", "room_type", "capacity", "equipment", "status"]


def list_rooms(db: Session):
    rows = db.execute(select(Room).order_by(Room.id)).scalars()
    return [row_to_dict(r) for r in rows]


def add_room(db: Session, form):
    values = {
        "room_id": clean_text(form.get("room_id"), "Room ID", 30),
        "name": clean_text(form.get("name"), "Name", 80),
        "building": clean_text(form.get("building"), "Building", 80, required=False),
        "room_type": clean_text(form.get("room_type"), "Room type", 60, required=False),
        "capacity": clean_text(form.get("capacity"), "Capacity", 10, required=False),
        "equipment": clean_text(form.get("equipment"), "Equipment", 200, required=False),
        "status": clean_text(form.get("status"), "Status", 40, required=False),
    }
    exists = db.execute(select(Room.id).where(
        func.lower(Room.room_id) == values["room_id"].lower())).first()
    if exists:
        raise ValidationError("That room ID already exists.")
    db.add(Room(**values))
    db.commit()


def delete_room(db: Session, row_id):
    row = db.get(Room, row_id)
    if row is not None:
        db.delete(row)
        db.commit()


def facility_names(db: Session):
    """Names for the reservation form suggestions."""
    return [r["name"] or r["room_id"] for r in list_rooms(db)]


def extract_room_code(question):
    """'projector in Room 204 is broken' -> '204'"""
    match = re.search(r"\broom\s*#?\s*([a-z]?\d{1,4}[a-z]?)\b", question.lower())
    return match.group(1).upper() if match else None


def find_room(db: Session, code):
    code = (code or "").lower()
    for r in list_rooms(db):
        if code and (r["room_id"].lower() == code or r["room_id"].lower() == f"room {code}"
                     or code in r["name"].lower().split()):
            return r
    return None


def room_reply(room):
    parts = [f'**{room["name"] or room["room_id"]}**']
    for label, key in (("Building", "building"), ("Type", "room_type"),
                       ("Capacity", "capacity"), ("Equipment", "equipment"),
                       ("Status", "status")):
        if room.get(key):
            parts.append(f"{label}: {room[key]}")
    return "\n".join(parts)
