"""
services/campus_service.py - campus information kept in the campus_info table
that admins can edit from the dashboard.

Columns: topic, keywords, answer
keywords are separated by ";"  and "a+b" means both words must appear.
"""

import csv
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.models import CampusInfo
from app.services.common import ValidationError, clean_text, row_to_dict


def normalize(text):
    text = (text or "").lower().replace("’", "").replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def seed_if_empty(db: Session):
    """Load starter facts from seed/campus_info.csv.

    Adds every seed topic that is not in the table yet, so new facts added to the
    CSV reach an existing database after a redeploy. Existing rows (including ones
    edited in the admin dashboard) are never changed.
    """
    if not config.CAMPUS_SEED_CSV.exists():
        return
    have = {t.lower() for t in db.execute(select(CampusInfo.topic)).scalars()}
    added = False
    with config.CAMPUS_SEED_CSV.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            topic = (row.get("topic") or "").strip()
            if topic and topic.lower() not in have:
                db.add(CampusInfo(topic=topic, keywords=row.get("keywords", ""),
                                  answer=row.get("answer", "")))
                have.add(topic.lower())
                added = True
    if added:
        db.commit()


def list_info(db: Session):
    rows = db.execute(select(CampusInfo).order_by(CampusInfo.id)).scalars()
    return [row_to_dict(r) for r in rows]


def add_info(db: Session, form):
    topic = clean_text(form.get("topic"), "Topic", 80)
    keywords = clean_text(form.get("keywords"), "Keywords", 200)
    answer = clean_text(form.get("answer"), "Answer", 600)
    exists = db.execute(select(CampusInfo.id).where(
        func.lower(CampusInfo.topic) == topic.lower())).first()
    if exists:
        raise ValidationError("That topic already exists.")
    db.add(CampusInfo(topic=topic, keywords=keywords, answer=answer))
    db.commit()


def delete_info(db: Session, row_id):
    row = db.get(CampusInfo, row_id)
    if row is not None:
        db.delete(row)
        db.commit()


def _has_phrase(q, phrase):
    return f" {phrase} " in f" {q} "


def lookup(db: Session, question):
    """Return the best matching campus answer, or None."""
    q = normalize(question)
    best, best_score = None, 0
    for row in list_info(db):
        score = 0
        for item in (row.get("keywords") or "").split(";"):
            parts = [normalize(p) for p in item.split("+") if normalize(p)]
            if parts and all(_has_phrase(q, p) for p in parts):
                score = max(score, sum(2 * len(p.split()) for p in parts))
        if score > best_score:
            best, best_score = row, score
    return best["answer"] if best else None