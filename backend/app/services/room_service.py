"""
services/room_service.py - room information (rooms table).

The table is empty at first. Admins add the real rooms from the dashboard,
so the AI never has to guess room details.
"""

import re

from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models import Room
from app.services.common import ValidationError, clean_text, row_to_dict

FIELDS = ["room_id", "name", "building", "department", "room_type", "capacity", "equipment", "status"]


def list_rooms(db: Session):
    rows = db.execute(select(Room).order_by(Room.id)).scalars()
    return [row_to_dict(r) for r in rows]


def list_rooms_page(db: Session, page=1, page_size=100, search="", department=""):
    query = select(Room)
    if department:
        query = query.where(or_(func.lower(Room.department) == department.lower(),
                                func.lower(Room.building) == department.lower()))
    if search:
        term = f"%{search.strip().lower()}%"
        query = query.where(or_(*(func.lower(cast(getattr(Room, field), String)).like(term)
                                  for field in FIELDS)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Room.id).offset((page - 1) * page_size).limit(page_size)).all()
    return [row_to_dict(row) for row in rows], total


def import_rooms(db: Session, records):
    """Validate a room CSV as a whole, then insert/update rows in one transaction."""
    existing = {row.room_id.lower(): row for row in db.scalars(select(Room)).all()}
    seen = set()
    prepared = []
    for line_number, record in enumerate(records, start=2):
        values = _room_values(record)
        key = values["room_id"].lower()
        if key in seen:
            raise ValidationError(f"Duplicate room ID on CSV row {line_number}: {values['room_id']}.")
        seen.add(key)
        prepared.append((key, values))
    for key, values in prepared:
        row = existing.get(key)
        if row is None:
            db.add(Room(**values))
        else:
            for field, value in values.items():
                setattr(row, field, value)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise ValidationError("Room import failed. No room changes were saved.")
    return len(prepared)


def count_rooms(db: Session):
    """Return the number of room records saved in the system."""
    return db.scalar(select(func.count(Room.id))) or 0


def add_room(db: Session, form):
    values = _room_values(form)
    exists = db.execute(select(Room.id).where(
        func.lower(Room.room_id) == values["room_id"].lower())).first()
    if exists:
        raise ValidationError("That room ID already exists.")
    db.add(Room(**values))
    db.commit()


def _room_values(form):
    return {
        "room_id": clean_text(form.get("room_id"), "Room ID", 30),
        "name": clean_text(form.get("name"), "Name", 80),
        "building": clean_text(form.get("building"), "Building", 80, required=False),
        "department": clean_text(form.get("department"), "Department", 80, required=False),
        "room_type": clean_text(form.get("room_type"), "Room type", 60, required=False),
        "capacity": clean_text(form.get("capacity"), "Capacity", 10, required=False),
        "equipment": clean_text(form.get("equipment"), "Equipment", 200, required=False),
        "status": clean_text(form.get("status"), "Status", 40, required=False),
    }


def update_room(db: Session, row_id, form):
    row = db.get(Room, row_id)
    if row is None:
        raise ValidationError("Room not found.")
    values = _room_values(form)
    exists = db.execute(select(Room.id).where(
        func.lower(Room.room_id) == values["room_id"].lower(), Room.id != row_id)).first()
    if exists:
        raise ValidationError("That room ID already exists.")
    for key, value in values.items():
        setattr(row, key, value)
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
    code = (code or "").strip().lower()
    if not code:
        return None
    row = db.execute(select(Room).where(func.lower(Room.room_id).in_((code, f"room {code}")))).scalar_one_or_none()
    if row is not None:
        return row_to_dict(row)
    candidates = retrieve_rooms(db, code, limit=10)
    return next((r for r in candidates if code in (r.get("name") or "").lower().split()), None)


def find_mentioned_room(db: Session, question):
    """Find a room by its ID or full name when either appears in a message."""
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).split())
    for room in retrieve_rooms(db, question, limit=20):
        aliases = [room.get("name", "")]
        room_id = (room.get("room_id") or "").strip()
        if room_id:
            aliases.append(room_id)
        for alias in aliases:
            alias = " ".join(re.sub(r"[^a-z0-9]+", " ", alias.lower()).split())
            if alias and re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized):
                return room
    return None


def is_room_location_question(question):
    """Recognize common location wording, including the typo 'were' for 'where'."""
    q = " ".join(re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).split())
    return (any(word in q.split() for word in ("where", "wheres", "were", "wher", "located", "locate", "location",
                                                "find", "found", "asa", "nasaan", "diin", "saan", "dapit","hain"))
            and any(word in q.split() for word in ("room", "classroom", "laboratory", "laboratories",
                                                    "lab", "labs", "this", "that", "it")))


def is_room_details_question(question):
    q = " ".join(re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).split())
    tokens = set(q.split())
    has_room_subject = bool(tokens & {"room", "rooms", "classroom", "classrooms", "laboratory", "laboratories", "lab", "labs"})
    asks_detail = bool(tokens & {"capacity", "equipment", "available", "availability", "status", "type",
                                 "details", "information", "department", "college", "unit", "belongs"})
    return has_room_subject and asks_detail


def is_room_information_question(question):
    q = " ".join(re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).split())
    tokens = set(q.split())
    has_room_subject = bool(tokens & {"room", "rooms", "classroom", "classrooms", "laboratory", "laboratories", "lab", "labs"})
    has_question_shape = bool(tokens & {"what", "which", "where", "wheres", "were", "how", "do", "does", "is", "are", "can", "have", "has", "available", "availability", "list", "show", "find", "tell"})
    detail_words = {"capacity", "equipment", "status", "type", "building", "projector", "projectors",
                    "computer", "computers", "pc", "pcs", "aircon", "air", "conditioning", "whiteboard",
                    "sound", "screen", "television", "tv", "laboratory", "laboratories", "lab", "labs",
                    "classroom", "classrooms", "cite", "ict", "cbm", "cas", "cte", "near", "gate", "canteen", "library",
                    "department", "departments", "college", "unit", "belongs", "belong"}
    return has_room_subject and has_question_shape and bool(tokens & detail_words)


def is_room_list_question(question):
    q = " ".join(re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).split())
    tokens = set(q.split())
    has_room_subject = bool(tokens & {"room", "rooms", "classroom", "classrooms", "laboratory", "laboratories", "lab", "labs"})
    asks_for_set = bool(tokens & {"available", "availability", "vacant", "free", "open", "list", "show", "all", "which", "any", "unoccupied"})
    specific_detail = bool(tokens & {"projector", "projectors", "computer", "computers", "pc", "pcs", "ac", "air", "aircon", "conditioning", "capacity", "equipment", "status", "type"})
    explicit_list = bool(tokens & {"list", "show", "all"})
    return has_room_subject and asks_for_set and (explicit_list or not specific_detail)


def list_room_preview(db: Session, limit=20):
    return [row_to_dict(row) for row in db.scalars(select(Room).order_by(Room.id).limit(limit)).all()]


_ROOM_RETRIEVAL_STOPWORDS = {
    "a", "about", "all", "an", "and", "are", "at", "can", "classroom",
    "classrooms", "do", "does", "find", "for", "have", "how", "i", "in", "is", "it", "me", "my",
    "of", "on", "or", "our", "please", "room", "rooms", "show", "the", "there", "this", "to",
    "today", "tell", "what", "when", "where", "wheres", "were", "which", "with", "you", "your",
    "capacity", "equipment", "status", "type", "details", "information", "located", "location", "near",
    "asa", "saan", "nasaan", "diin", "dapit", "ang", "sa", "naa", "naay", "ba", "bay", "mga", "nga", "unsa", "unsay",
}
_ROOM_SYNONYMS = {
    "labs": {"lab", "laboratory"}, "lab": {"laboratory"}, "laboratories": {"laboratory", "lab"},
    "computers": {"computer", "pcs", "pc"}, "computer": {"computers", "pcs"},
    "projectors": {"projector"}, "projector": {"projectors"}, "ac": {"air conditioning", "aircon"},
    "aircon": {"ac", "air conditioning"}, "air": {"aircon", "ac"},
    "vacant": {"available", "free"}, "free": {"available", "vacant"},
}
_ROOM_SEARCH_FIELDS = ((Room.room_id, 12), (Room.name, 8), (Room.building, 5), (Room.department, 5),
                       (Room.room_type, 4), (Room.equipment, 4), (Room.status, 2), (Room.capacity, 2))


def retrieve_rooms(db: Session, question, limit=5):
    """Lexically retrieve a small, ranked set of room records for grounded answers."""
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).split())
    terms = []
    for word in normalized.split():
        if word in _ROOM_RETRIEVAL_STOPWORDS or len(word) < 2:
            continue
        terms.append(word)
        terms.extend(_ROOM_SYNONYMS.get(word, ()))
    terms = list(dict.fromkeys(terms))[:12]
    if not terms:
        return []

    matches = []
    score = None
    for term in terms:
        for column, weight in _ROOM_SEARCH_FIELDS:
            condition = column.ilike(f"%{term}%")
            matches.append(condition)
            weighted_hit = case((condition, weight), else_=0)
            score = weighted_hit if score is None else score + weighted_hit
    query = (select(Room).where(or_(*matches)).order_by(score.desc(), Room.id).limit(max(1, min(int(limit), 100))))
    rows = [row_to_dict(row) for row in db.scalars(query).all()]
    if any(word in normalized.split() for word in ("available", "availability", "vacant", "free", "open", "unoccupied")):
        available = [row for row in rows if _is_free(row)]
        if available:
            return available
    return rows


def room_location_reply(room):
    room_id = room.get("room_id") or ""
    room_label = room_id if room_id.lower().startswith("room ") else f"Room {room_id}"
    name = room.get("name") or room_label
    building = room.get("building")
    if building:
        return (f"**{name}** ({room_label}) is in **{building}**. The room record doesn't "
                "include a floor or nearby landmark, so I can't give a more precise location.")
    return f"I found **{name}** ({room_label}), but its building location hasn't been added yet."


def room_locations_reply(rooms):
    """List locations for matching rooms when a name refers to more than one room."""
    unique = {}
    for room in rooms:
        key = (room.get("room_id") or room.get("name") or "").lower()
        if key:
            unique[key] = room
    rooms = list(unique.values())
    if len(rooms) == 1:
        return room_location_reply(rooms[0])
    locations = sorted({room.get("building") for room in rooms if room.get("building")})
    if not locations:
        names = ", ".join(f"**{room.get('name') or room.get('room_id')}**" for room in rooms)
        return f"I found {names}, but their building locations haven't been added yet."
    location_text = ", ".join(f"**{location}**" for location in locations)
    listing = "\n".join(
        f"- **{room.get('name') or room.get('room_id')}** (Room {room.get('room_id')})"
        for room in rooms)
    return (f"These rooms are listed in {location_text}:\n{listing}\n"
            "The room records don't include a floor or nearby landmark.")


def room_reply(room):
    room_id = str(room.get("room_id") or "").strip()
    room_label = room_id if room_id.lower().startswith("room ") else f"Room {room_id}"
    name = room.get("name") or room_label
    parts = [f"**{name}** ({room_label})"]
    for label, key in (("Building", "building"), ("Department", "department"), ("Type", "room_type"),
                       ("Capacity", "capacity"), ("Equipment", "equipment"),
                       ("Status", "status")):
        if room.get(key):
            parts.append(f"{label}: {room[key]}")
    return "\n".join(parts)


def room_department_reply(room):
    """Answer department questions from the room's recorded fields."""
    room_id = room.get("room_id") or ""
    label = room_id if room_id.lower().startswith("room ") else f"Room {room_id}"
    name, building = room.get("name"), room.get("building")
    department = room.get("department")
    details = []
    if name:
        details.append(f"listed as **{name}**")
    if building:
        details.append(f"in **{building}**")
    if department:
        details.append(f"assigned to **{department}**")
    if not details:
        return f"I found {label}, but its room record doesn't include a department or building."
    reply = f"{label} is " + " ".join(details) + "."
    if not department:
        reply += " Its department has not been recorded separately."
    return reply


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
    department = r.get("department")
    building = r.get("building")
    details = [x for x in (f"department {department}" if department and department.lower() != (building or "").lower() else "",
                           building, r.get("room_type"),
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
        match_words = set(words)
        for word in words:
            match_words.update(_ROOM_SYNONYMS.get(word, ()))
        match_words = {part for word in match_words for part in word.split()}
        def matches(r):
            text = f" {r['building']} {r.get('department', '')} {r['name']} {r['room_id']} {r['room_type']} {r['equipment']} {r['capacity']} {r['status']} ".lower()
            text = " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())
            return any(f" {w} " in f" {text} " for w in match_words)
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
