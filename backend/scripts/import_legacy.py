"""
scripts/import_legacy.py - move the data of the OLD Flask version into PostgreSQL.

Run from the backend/ folder, for example:

    python -m scripts.import_legacy \
        --sqlite ../old/database/campus.db \
        --faculty-csv ../old/data/faculty/faculty_availability.csv \
        --rooms-csv ../old/data/rooms/rooms.csv \
        --campus-csv ../old/data/campus/campus_info.csv

Every option is optional. The script can be run again safely: rows that already
exist (same id / topic / room id) are skipped. Old admin password hashes are NOT
imported (a different hashing library is used now) - run
`python -m scripts.create_admin` or set ADMIN_PASSWORD in backend/.env.
"""

import argparse
import csv
import re
import sqlite3
from datetime import date, datetime, time
from pathlib import Path

from sqlalchemy import func, select, text

from app.database import SessionLocal, init_db
from app.models import (CampusInfo, Concern, FacultyReport, Feedback, Report,
                        Reservation, Room, User)


# ------------------------------------------------------------- converters
def _dt(value):
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return datetime.now().replace(microsecond=0)


def _date(value):
    return _dt(value).date()


def _time(value):
    value = (value or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            pass
    return time(0, 0)


def _reset_sequence(db, table):
    db.execute(text(
        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
        f"COALESCE((SELECT MAX(id) FROM {table}), 1), (SELECT MAX(id) FROM {table}) IS NOT NULL)"))


# ----------------------------------------------------------------- SQLite
def import_sqlite(db, path):
    src = sqlite3.connect(path)
    src.row_factory = sqlite3.Row
    counts = {}

    def rows(table):
        try:
            return src.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        except sqlite3.OperationalError:
            return []

    def add(model, table, build):
        n = 0
        for r in rows(table):
            if db.get(model, r["id"]) is None:
                db.add(build(r))
                n += 1
        db.flush()
        counts[table] = n

    add(User, "users", lambda r: User(
        id=r["id"], google_id=r["google_id"], name=r["name"], email=r["email"], role=r["role"],
        created_at=_dt(r["created_at"]), last_login=_dt(r["last_login"]),
        is_active=bool(r["is_active"])))
    add(Concern, "concerns", lambda r: Concern(
        id=r["id"], user_id=r["user_id"], reporter_name=r["reporter_name"],
        reporter_email=r["reporter_email"], location=r["location"], room=r["room"],
        concern_type=r["concern_type"], description=r["description"],
        concern_date=_date(r["concern_date"]), image_filename=r["image_filename"],
        status=r["status"], created_at=_dt(r["created_at"]), updated_at=_dt(r["updated_at"])))
    add(Report, "reports", lambda r: Report(
        id=r["id"], user_id=r["user_id"], reporter_name=r["reporter_name"],
        reporter_email=r["reporter_email"], location=r["location"], area=r["area"], room=r["room"],
        report_type=r["report_type"], description=r["description"],
        report_date=_date(r["report_date"]), image_filename=r["image_filename"],
        status=r["status"], created_at=_dt(r["created_at"]), updated_at=_dt(r["updated_at"])))
    add(Feedback, "feedback", lambda r: Feedback(
        id=r["id"], user_id=r["user_id"], name=r["name"], email=r["email"], area=r["area"],
        feedback_type=r["feedback_type"], message=r["message"],
        feedback_date=_date(r["feedback_date"]), status=r["status"],
        created_at=_dt(r["created_at"]), updated_at=_dt(r["updated_at"])))
    add(Reservation, "reservations", lambda r: Reservation(
        id=r["id"], user_id=r["user_id"], requester_name=r["requester_name"],
        requester_email=r["requester_email"], facility=r["facility"], purpose=r["purpose"],
        reservation_date=_date(r["reservation_date"]), start_time=_time(r["start_time"]),
        end_time=_time(r["end_time"]), additional_info=r["additional_info"], status=r["status"],
        created_at=_dt(r["created_at"]), updated_at=_dt(r["updated_at"])))
    src.close()
    return counts


# -------------------------------------------------------------------- CSV
def _read_faculty_csv(path):
    """Same repairs the old app did: glued header line, missing/duplicate ids."""
    raw = Path(path).read_text(encoding="utf-8-sig")
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    match = re.match(r"^(id,instructor,[a-z_,]*?status)(\d+,.*)$", lines[0]) if lines else None
    if match:
        lines[0:1] = [match.group(1), match.group(2)]
    rows = [dict(r) for r in csv.DictReader(lines) if r and r.get("instructor")]

    seen, next_id = set(), 1
    for row in rows:
        digits = re.sub(r"\D", "", row.get("id") or "")
        rid = int(digits) if digits else 0
        if not rid or rid in seen:
            while next_id in seen:
                next_id += 1
            rid = next_id
        seen.add(rid)
        row["id"] = rid
    return rows


def import_faculty(db, path):
    n = 0
    for row in _read_faculty_csv(path):
        if db.get(FacultyReport, row["id"]) is not None:
            continue
        db.add(FacultyReport(
            id=row["id"], instructor=row["instructor"].strip(), reason=(row.get("reason") or "").strip(),
            start_date=_date(row.get("start_date")), expected_return=_date(row.get("expected_return")),
            submitted_at=_dt(row.get("submitted_at")), status=(row.get("status") or "Absent").strip(),
            instructor_email=(row.get("instructor_email") or "").strip().lower()))
        n += 1
    db.flush()
    return n


def import_rooms(db, path):
    n = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            room_id = (row.get("room_id") or "").strip()
            if not room_id or db.execute(select(Room.id).where(
                    func.lower(Room.room_id) == room_id.lower())).first():
                continue
            db.add(Room(room_id=room_id, name=(row.get("name") or room_id).strip(),
                        building=(row.get("building") or "").strip(),
                        room_type=(row.get("room_type") or "").strip(),
                        capacity=(row.get("capacity") or "").strip(),
                        equipment=(row.get("equipment") or "").strip(),
                        status=(row.get("status") or "").strip()))
            n += 1
    db.flush()
    return n


def import_campus(db, path):
    n = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            topic = (row.get("topic") or "").strip()
            if not topic or db.execute(select(CampusInfo.id).where(
                    func.lower(CampusInfo.topic) == topic.lower())).first():
                continue
            db.add(CampusInfo(topic=topic, keywords=(row.get("keywords") or "").strip(),
                              answer=(row.get("answer") or "").strip()))
            n += 1
    db.flush()
    return n


def main():
    parser = argparse.ArgumentParser(description="Import old CampusSense AI data into PostgreSQL.")
    parser.add_argument("--sqlite", help="old database/campus.db")
    parser.add_argument("--faculty-csv", help="old data/faculty/faculty_availability.csv")
    parser.add_argument("--rooms-csv", help="old data/rooms/rooms.csv")
    parser.add_argument("--campus-csv", help="old data/campus/campus_info.csv")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        if args.sqlite:
            for table, n in import_sqlite(db, args.sqlite).items():
                print(f"  {table:<14} +{n}")
        if args.faculty_csv:
            print(f"  faculty_reports +{import_faculty(db, args.faculty_csv)}")
        if args.rooms_csv:
            print(f"  rooms          +{import_rooms(db, args.rooms_csv)}")
        if args.campus_csv:
            print(f"  campus_info    +{import_campus(db, args.campus_csv)}")
        for table in ("users", "concerns", "reports", "feedback", "reservations",
                      "faculty_reports", "rooms", "campus_info"):
            _reset_sequence(db, table)
        db.commit()
    print("Done.")


if __name__ == "__main__":
    main()
