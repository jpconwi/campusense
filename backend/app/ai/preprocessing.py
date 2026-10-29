"""Local preprocessing for student messages before intent classification.

This module keeps typo cleanup separate from intent routing and campus answers.
It uses only the vocabulary already stored in the campus dataset; it does not
send student messages to an external grammar service or rewrite their meaning.
"""

import difflib
import re

from sqlalchemy import select

from app.models import CampusInfo


FILLER = {
    "a", "an", "the", "of", "is", "are", "was", "were", "what", "whats", "who", "where",
    "when", "why", "how", "do", "does", "did", "can", "tell", "me", "about", "give",
    "show", "please", "pls", "to", "in", "on", "for", "and", "or", "i", "my", "you",
    "your", "it", "this", "that", "info", "information", "there", "any", "some",
}
GENERIC = {"nemsu", "campus", "university", "tandag", "school"}


def normalize(text):
    text = (text or "").lower().replace("\u2019", "").replace("\u00e2\u20ac\u2122", "").replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def row_vocabulary(row):
    words = set(normalize(row.get("topic")).split())
    for item in (row.get("keywords") or "").split(";"):
        for part in item.split("+"):
            words.update(normalize(part).split())
    return words


def correct_spelling(rows, question):
    """Correct only high-confidence single-word typos against campus data."""
    known = set(FILLER) | GENERIC
    for row in rows:
        known.update(row_vocabulary(row))
    known = sorted(known)
    output = []
    for word in normalize(question).split():
        if word not in known and len(word) >= 3:
            cutoff = 0.85 if len(word) <= 4 else 0.8
            match = difflib.get_close_matches(word, known, n=1, cutoff=cutoff)
            word = match[0] if match else word
        output.append(word)
    return " ".join(output)


def correct_question(db, question):
    """Load the current campus vocabulary and clean a question for intent matching."""
    records = db.execute(select(CampusInfo.topic, CampusInfo.keywords)).all()
    rows = [{"topic": topic, "keywords": keywords} for topic, keywords in records]
    return correct_spelling(rows, question)


def word_hit(word, vocabulary):
    """Return 2 for exact, 1 for close spelling, or 0 for no vocabulary match."""
    if word in vocabulary:
        return 2
    if len(word) < 3:
        return 0
    cutoff = 0.85 if len(word) <= 4 else 0.8
    return 1 if difflib.get_close_matches(word, vocabulary, n=1, cutoff=cutoff) else 0
