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


# ------------------------------------------------------------ room lists
_ROOM_STOPWORDS = {
    "what", "are", "is", "the", "available", "availability", "rooms", "room", "classroom",
    "classrooms", "in", "at", "of", "any", "there", "list", "show", "me", "all", "which",
    "vacant", "free", "open", "now", "today", "right", "can", "i", "use", "building", "a",
    "an", "and", "for", "do", "you", "have", "unoccupied", "currently", "tell", "nemsu",
    "campus", "tandag", "please", "to", "on", "my", "our", "need", "looking", "find",
}
_FREE_WORDS = ("avail", "vacant", "free", "open", "unoccupied")


def _is_free(room):
    status = (room.get("status") or "").lower()
    return any(w in status for w in _FREE_WORDS) and "not " not in status \
        and "unavail" not in status


def _room_line(r):
    details = [x for x in (r.get("building"), r.get("room_type"),
                           f"capacity {r['capacity']}" if r.get("capacity") else "",
                           r.get("equipment")) if x]
    status = r.get("status") or "status not set"
    return f"- **{r['name'] or r['room_id']}** ({r['room_id']}): " + \
        ", ".join(details + [status])


def rooms_answer(rooms, question_words, wants_available):
    """Pure function (easy to test): rooms = list of room dicts, question_words = tokens."""
    if not rooms:
        return ("There are no rooms in the campus room list yet. An administrator can add "
                "them in the admin dashboard under Rooms.")
    words = [w for w in question_words if w not in _ROOM_STOPWORDS and len(w) > 1]
    scope = ""
    if words:
        def matches(r):
            text = f" {r['building']} {r['name']} {r['room_id']} {r['room_type']} ".lower()
            text = " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())
            return any(f" {w} " in f" {text} " for w in words)
        found = [r for r in rooms if matches(r)]
        if not found:
            buildings = sorted({r["building"] for r in rooms if r["building"]})
            hint = f" Rooms are recorded for: {', '.join(buildings)}." if buildings else ""
            return f"I don't have any rooms recorded for \"{' '.join(words)}\".{hint}"
        rooms, scope = found, f" in {' '.join(words).upper()}"
    if wants_available:
        free = [r for r in rooms if _is_free(r)]
        if free:
            return f"Available rooms{scope}:\n" + "\n".join(_room_line(r) for r in free[:20]) + \
                (f"\n...and {len(free) - 20} more." if len(free) > 20 else "")
        return (f"No room{scope} is marked as available right now. Here are the rooms "
                f"I have{scope}:\n" + "\n".join(_room_line(r) for r in rooms[:20]))
    return f"Rooms{scope}:\n" + "\n".join(_room_line(r) for r in rooms[:20]) + \
        (f"\n...and {len(rooms) - 20} more." if len(rooms) > 20 else "")
