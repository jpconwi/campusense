"""
services/announcement_service.py - announcements the admin feeds to the AI.

Examples: school news, events, champions, "the local MAST starts on ...".
Each one has a title, a category, a message, and an optional "show from" and
"show until" date. Only ACTIVE announcements are told to users.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Announcement
from app.services.common import ValidationError, clean_choice, clean_date, clean_text, row_to_dict

CATEGORIES = ["Announcement", "Event", "Champions", "News", "Update"]

LABELS = {None: "announcements", "Event": "events", "Champions": "champion announcements",
          "News": "news", "Update": "updates", "Announcement": "announcements"}


def _today():
    return datetime.now().date().strftime("%Y-%m-%d")


def status_of(row, today=None):
    today = today or _today()
    if row.get("start_date") and row["start_date"] > today:
        return "Scheduled"
    if row.get("end_date") and row["end_date"] < today:
        return "Expired"
    return "Active"


def list_all(db: Session):
    """Newest first, for the admin page (with an Active / Scheduled / Expired status)."""
    rows = db.execute(select(Announcement).order_by(Announcement.id.desc())).scalars()
    result = []
    for r in rows:
        data = row_to_dict(r)
        data["status"] = status_of(data)
        result.append(data)
    return result


def list_active(db: Session):
    return [r for r in list_all(db) if r["status"] == "Active"]


def add_announcement(db: Session, form):
    title = clean_text(form.get("title"), "Title", 120)
    category = clean_choice(form.get("category"), "Category", CATEGORIES)
    body = clean_text(form.get("body"), "Message", 1000)
    start = clean_date(form["start_date"], "Show from") if (form.get("start_date") or "").strip() else None
    end = clean_date(form["end_date"], "Show until") if (form.get("end_date") or "").strip() else None
    if start and end and end < start:
        raise ValidationError("The end date cannot be before the start date.")
    db.add(Announcement(title=title, category=category, body=body,
                        start_date=start, end_date=end))
    db.commit()


def delete_announcement(db: Session, row_id):
    row = db.get(Announcement, row_id)
    if row is not None:
        db.delete(row)
        db.commit()


# ------------------------------------------------------------ answers (pure functions)
def _one(r):
    return f"**{r['title']}** ({r['category']})\n{r['body']}"


def format_reply(rows, label="announcements"):
    if not rows:
        return f"There are no {label} posted right now."
    text = f"Here are the latest {label}:\n\n" + "\n\n".join(_one(r) for r in rows[:5])
    if len(rows) > 5:
        text += f"\n\n...and {len(rows) - 5} more."
    return text


def chat_reply(db: Session, category=None):
    rows = list_active(db)
    if category:
        rows = [r for r in rows if r["category"] == category]
    return format_reply(rows, LABELS.get(category, "announcements"))


_STOP = {
    "the", "and", "for", "are", "was", "were", "what", "when", "where", "who", "how", "why",
    "does", "did", "has", "have", "will", "can", "you", "your", "our", "this", "that", "there",
    "about", "tell", "please", "any", "with", "from", "into", "than", "then", "its", "his",
    "her", "they", "them", "now", "today", "tomorrow", "nemsu", "campus", "tandag", "school",
    "university", "start", "starts", "date", "time", "held", "happening", "know", "want",
    "need", "get", "give", "show", "list", "latest", "new", "next", "upcoming", "currently",
}


def _stem(word):
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def best_match(rows, q):
    """Pick the active announcement a free question is about, or None.

    q is the normalized question. A word in the title counts 2, a word in the
    message counts 1, and at least 3 points are needed, so general questions
    ("when does the semester start") are not answered with an unrelated post.
    """
    words = [_stem(w) for w in q.split() if len(w) > 2 and w not in _STOP]
    if not words:
        return None
    best, best_score = None, 0
    for r in rows:
        title = {_stem(w) for w in _norm(r["title"]).split()}
        body = {_stem(w) for w in _norm(r["body"]).split()}
        score = sum(2 if w in title else 1 for w in set(words) if w in title or w in body)
        if score > best_score:
            best, best_score = r, score
    return best if best_score >= 3 else None


def _norm(text):
    import re
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower().replace("'", "")).split())


def match(db: Session, q):
    row = best_match(list_active(db), q)
    return _one(row) if row else None


def for_prompt(rows):
    """Lines for the language model, so it can mention announcements."""
    return "\n".join(f"- [{r['category']}] {r['title']}: {r['body']}"
                     + (f" (until {r['end_date']})" if r.get("end_date") else "") for r in rows)
