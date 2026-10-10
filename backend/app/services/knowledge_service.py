"""
services/knowledge_service.py - lets the chatbot use the NEMSU articles saved in
`knowledge_documents` (news from the Newsroom, later memos / Facebook / PDFs).

Simple keyword search (no embeddings, no new services):
  * a word that appears in the article TITLE counts 3, in the BODY counts 1
  * a document needs at least 2 different matching words and a score of 5, so
    unrelated questions never pull in an article
  * the best passages of the best documents are given to the language model,
    which is told to answer ONLY from them
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeDocument
from app.services.campus_service import normalize

MAX_DOCS = 3                 # articles given to the AI per question
MAX_CHARS_PER_DOC = 1200     # passage length per article
MIN_SCORE = 5
SCAN_LIMIT = 600             # newest documents that are searched

STOP = {
    "the", "and", "for", "are", "was", "were", "what", "when", "where", "who", "how", "why",
    "does", "did", "has", "have", "will", "can", "you", "your", "our", "this", "that", "there",
    "about", "tell", "please", "any", "with", "from", "into", "than", "then", "its", "his",
    "her", "they", "them", "now", "today", "tomorrow", "know", "want", "need", "get", "give",
    "show", "list", "philippine", "philippines", "filipino", "time", "year", "years", "date",
    "day", "week", "month", "now", "latest", "new", "next", "upcoming", "currently", "news", "update",
    "updates", "nemsu", "campus", "tandag", "school", "university", "is", "in", "of", "to",
    "a", "an", "on", "at", "be", "me", "my", "it", "do", "i", "or", "by", "as",
    # common Filipino / Bisaya filler words
    "ang", "ng", "sa", "mga", "ba", "ko", "mo", "na", "pa", "po", "ano", "unsa", "kay",
    "naa", "nga", "ni", "si", "ug", "og", "para", "ito", "yung", "yang", "mag", "kung",
}


def _stem(word):
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def keywords(question):
    """Meaningful words of a question (lower case, simple plural stripping)."""
    words = [w for w in normalize(question).split() if len(w) > 2 and w not in STOP]
    return list(dict.fromkeys(_stem(w) for w in words))


def _words(text):
    return {_stem(w) for w in normalize(text).split()}


def score(words, title, content):
    """(score, matched) for one document."""
    t, c = _words(title), _words(content)
    matched = [w for w in words if w in t or w in c]
    # a word in the title is worth 3, and 1 more if the body also has it; body only = 1
    points = sum((3 + (1 if w in c else 0)) if w in t else 1 for w in matched)
    ok = len(matched) >= 2 and points >= MIN_SCORE
    return (points if ok else 0), matched


def best_passage(content, words, limit=MAX_CHARS_PER_DOC):
    """The paragraphs of an article that mention most of the question's words."""
    parts = [p.strip() for p in (content or "").split("\n") if p.strip()]
    if not parts:
        return ""
    if sum(len(p) for p in parts) <= limit:
        return "\n".join(parts)
    ranked = sorted(range(len(parts)),
                    key=lambda i: (-sum(1 for w in words if w in _words(parts[i])), i))
    chosen, used = [], 0
    for i in ranked:
        piece = len(parts[i]) + 1
        if used + piece > limit:
            if not chosen:                      # one huge paragraph: cut it
                parts[i] = parts[i][:limit - 1]
                chosen.append(i)
            continue
        chosen.append(i)
        used += piece
    return "\n".join(parts[i] for i in sorted(chosen))


def rank(rows, question, limit=MAX_DOCS):
    """rows: dicts with title/content/source_url/published_at -> best matches first."""
    words = keywords(question)
    if not words:
        return []
    hits = []
    for r in rows:
        points, matched = score(words, r["title"], r["content"])
        if points:
            hits.append((points, r["published_at"] or 0, r, matched))
    hits.sort(key=lambda h: (-h[0], -(h[1].timestamp() if h[1] else 0)))
    return [dict(h[2], score=h[0], passage=best_passage(h[2]["content"], h[3]))
            for h in hits[:limit]]


def _rows(db: Session, limit=SCAN_LIMIT):
    q = select(KnowledgeDocument.title, KnowledgeDocument.content, KnowledgeDocument.source_url,
               KnowledgeDocument.published_at, KnowledgeDocument.source_type) \
        .order_by(KnowledgeDocument.published_at.desc().nullslast(),
                  KnowledgeDocument.id.desc()).limit(limit)
    return [dict(title=t, content=c, source_url=u, published_at=p, source_type=s)
            for t, c, u, p, s in db.execute(q)]


def search(db: Session, question, limit=MAX_DOCS):
    return rank(_rows(db), question, limit)


def latest(db: Session, limit=3):
    return _rows(db, limit)


def _date(d):
    return d["published_at"].strftime("%b %d, %Y").replace(" 0", " ") if d.get("published_at") else ""


def for_prompt(docs):
    """Text block that goes into the AI's system prompt."""
    blocks = []
    for i, d in enumerate(docs, 1):
        blocks.append(f"[{i}] {d['title']} ({_date(d) or 'no date'})\n{d['passage']}")
    return (
        "OFFICIAL NEMSU NEWS (collected from the NEMSU Newsroom). Answer the question ONLY "
        "from these articles. If they do not contain the answer, say you could not find it "
        "in the latest NEMSU news. Never invent names, dates or numbers.\n\n"
        + "\n\n".join(blocks))


def sources_text(docs):
    """Source lines added under the answer so students can open the full article."""
    lines = [f"- {d['title']}" + (f" ({_date(d)})" if _date(d) else "") + f"\n  {d['source_url']}"
             for d in docs]
    return "Source" + ("s" if len(docs) > 1 else "") + ":\n" + "\n".join(lines)


def fallback_answer(docs):
    """Used when the language model is unavailable: show the best article directly."""
    d = docs[0]
    text = d["passage"]
    if len(text) > 700:                          # cut at the end of a sentence, never mid-word
        cut = text[:700]
        end = max(cut.rfind(". "), cut.rfind(".\n"), cut.rfind("! "), cut.rfind("? "))
        text = (cut[:end + 1] if end > 250 else cut.rsplit(" ", 1)[0]).rstrip() + (
            "" if end > 250 else "...")
    return f"Here is what I found in the NEMSU news:\n\n{d['title']}\n{text}"


def latest_text(docs):
    lines = [f"- {d['title']}" + (f" ({_date(d)})" if _date(d) else "") + f"\n  {d['source_url']}"
             for d in docs]
    return "Latest from the NEMSU Newsroom:\n" + "\n".join(lines)