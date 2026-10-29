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
from app.ai import preprocessing
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
    keywords = clean_text(form.get("keywords"), "Keywords", 500)
    answer = clean_text(form.get("answer"), "Answer", 2000)
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
    """Return the best matching campus answer, or None.

    Misspelt words are corrected first, and words that only say "nemsu"/"what is"
    count for little, so "what is nemsu hymn" finds the hymn, not "About NEMSU"."""
    rows = list_info(db)
    q = normalize(preprocessing.correct_spelling(rows, question))
    best, best_score = None, 0
    for row in rows:
        score = 0
        for item in (row.get("keywords") or "").split(";"):
            parts = [normalize(p) for p in item.split("+") if normalize(p)]
            if parts and all(_has_phrase(q, p) for p in parts):
                score = max(score, sum(_phrase_weight(p) for p in parts))
        if score > best_score:
            best, best_score = row, score
    return best["answer"] if best else None


def _phrase_weight(phrase):
    """Real topic words count 2 each; filler/generic-only phrases ("what is nemsu") count 1."""
    real = [w for w in phrase.split()
            if w not in preprocessing.FILLER and w not in preprocessing.GENERIC]
    return 2 * len(real) if real else 1


def _rank_rows(db, question):
    """[(score, row)] best first, for rows sharing at least one real word
    (exact or misspelt) with the question. Used for typo matching and suggestions."""
    words = [w for w in normalize(question).split()
             if w not in preprocessing.FILLER and len(w) >= 3]
    key = [w for w in words if w not in preprocessing.GENERIC]
    ranked = []
    if not key:
        return ranked
    for row in list_info(db):
        vocab = list(preprocessing.row_vocabulary(row))
        hits = [preprocessing.word_hit(w, vocab) for w in key]
        matched = sum(1 for h in hits if h)
        if not matched:
            continue
        coverage = matched / len(key)
        ranked.append((coverage * 10 + sum(hits), coverage, row))
    ranked.sort(key=lambda t: -t[0])
    return ranked


def lookup_fuzzy(db, question):
    """Answer for a misspelt question (\"nemsu hym\" -> hymn, \"nemsu policy\" ->
    quality policy). Only answers when ONE topic is clearly the best match."""
    ranked = _rank_rows(db, question)
    if not ranked:
        return None
    score, coverage, row = ranked[0]
    if coverage < 0.6:
        return None
    if len(ranked) > 1 and ranked[1][0] >= score - 0.5:     # two topics tie -> ask instead
        return None
    return row["answer"]


def suggest_topics(db, question, limit=3):
    """Topic names the user probably meant; shown as 'Did you mean ...?' buttons."""
    return [row["topic"] for _, cov, row in _rank_rows(db, question) if cov >= 0.5][:limit]
