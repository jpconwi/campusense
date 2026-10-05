"""
services/faculty_service.py - faculty availability (faculty_reports table, NOT the LLM).

The AI never guesses availability. The answer always comes from this table.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.models import FacultyReport
from app.services.common import (ValidationError, clean_date, clean_text, now,
                                 row_to_dict)
from app.services.pdf_service import generate_pdf


def _to_dict(obj):
    data = row_to_dict(obj)
    data["display_id"] = f"{obj.id:04d}"
    return data


def load_records(db: Session):
    """All records, oldest first (the newest is last)."""
    rows = db.execute(select(FacultyReport).order_by(FacultyReport.id)).scalars()
    return [_to_dict(r) for r in rows]


def pdf_path(record_id):
    return config.REPORTS_DIR / "faculty" / f"faculty_report_{int(record_id):04d}.pdf"


# ------------------------------------------------------- submit / update
def create_faculty_report(db: Session, user, form):
    """Save an absence report for the logged-in instructor and make a PDF."""
    reason = clean_text(form.get("reason"), "Reason", 300)
    start_date = clean_date(form.get("start_date"), "Date of absence")
    expected_return = clean_date(form.get("expected_return"), "Expected return date")
    if expected_return < start_date:
        raise ValidationError("The return date cannot be before the date of absence.")

    row = FacultyReport(instructor=user.name,                 # from the Google account
                        reason=reason, start_date=start_date, expected_return=expected_return,
                        submitted_at=now(), status="Absent", instructor_email=user.email.lower())
    db.add(row)
    db.commit()
    data = _to_dict(row)

    generate_pdf(pdf_path(row.id), "Faculty Availability Report", [
        ("Report ID", data["display_id"]), ("Instructor", data["instructor"]),
        ("Reason", data["reason"]), ("Date of Absence", data["start_date"]),
        ("Expected Return", data["expected_return"]),
        ("Submitted At", data["submitted_at"]), ("Status", data["status"]),
    ])
    return data


def mark_available_for_email(db: Session, email):
    """An instructor says 'I am back'. Only their own Absent records change."""
    rows = db.execute(select(FacultyReport).where(
        FacultyReport.instructor_email == email.lower(),
        FacultyReport.status == "Absent")).scalars().all()
    for row in rows:
        row.status = "Available"
    db.commit()
    return len(rows)


def mark_available_by_id(db: Session, record_id):
    """Used by the admin dashboard."""
    row = db.get(FacultyReport, record_id)
    if row is None or row.status != "Absent":
        return False
    row.status = "Available"
    db.commit()
    return True


def records_for_email(db: Session, email):
    return [r for r in reversed(load_records(db)) if r["instructor_email"] == email.lower()]


def get_record(db: Session, record_id):
    row = db.get(FacultyReport, record_id)
    return _to_dict(row) if row else None


# --------------------------------------------------------- name matching
def normalize_text(text):
    text = (text or "").lower().replace("’", "").replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _initials(name):
    return "".join(p[0] for p in normalize_text(name).split() if p)


def match_rank(search, instructor):
    """0 = no match, 3 = exact, 2 = full words, 1 = initials / partial."""
    s, i = normalize_text(search), normalize_text(instructor)
    if not s or not i:
        return 0
    if s == i:
        return 3
    if f" {s} " in f" {i} ":
        return 2
    s_words, i_words = s.split(), i.split()
    if all(w in i_words for w in s_words):
        return 2
    compact = s.replace(" ", "")
    if len(compact) >= 2 and _initials(i).startswith(compact):
        return 1
    if len(s_words) == 2 and i_words[-1] == s_words[-1] and i_words[0].startswith(s_words[0]):
        return 1
    return 0


def find_current_records(db: Session, search_name):
    """
    Best matching instructors, one (newest) record each.
    Returns a list of records. Empty list = no record.
    """
    rows = list(reversed(load_records(db)))             # newest first
    ranked = [(match_rank(search_name, r["instructor"]), r) for r in rows]
    ranked = [(rank, r) for rank, r in ranked if rank > 0]
    if not ranked:
        return []
    top = max(rank for rank, _ in ranked)
    latest, seen = [], set()
    for rank, r in ranked:
        key = normalize_text(r["instructor"])
        if rank == top and key not in seen:
            seen.add(key)
            latest.append(r)
    return latest[:3]


def has_record(db: Session, search_name):
    return bool(find_current_records(db, search_name))


def _status_sentence(row):
    name = row["instructor"]
    status = (row.get("status") or "").strip().lower()
    if status == "available":
        return f"{name} is currently recorded as available."
    if status == "absent":
        if row.get("expected_return"):
            return (f"{name} is currently unavailable. The recorded expected "
                    f"return date is {row['expected_return']}.")
        return f"{name} is currently recorded as unavailable."
    return f"{name} has an availability record, but no valid current status is recorded."


def availability_reply(db: Session, search_name):
    records = find_current_records(db, search_name)
    if not records:
        return f"I don't have an availability record for {search_name}."
    return "\n".join(_status_sentence(r) for r in records)


def return_reply(db: Session, search_name):
    records = find_current_records(db, search_name)
    if not records:
        return f"I don't have an availability record for {search_name}."
    lines = []
    for r in records:
        if (r.get("status") or "").lower() == "absent" and r.get("expected_return"):
            lines.append(f"{r['instructor']} is expected to return on {r['expected_return']}.")
        elif (r.get("status") or "").lower() == "available":
            lines.append(f"{r['instructor']} is currently recorded as available. "
                         "There is no active absence.")
        else:
            lines.append(f"There is no recorded return date for {r['instructor']}.")
    return "\n".join(lines)
