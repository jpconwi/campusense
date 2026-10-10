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
PAGE_MIN_SCORE = 4          # official website pages: one strong title word is enough
PAGE_CHARS_PER_DOC = 2500   # official pages are longer, so give the AI more of them
OFFICIAL = "nemsu_page"
SCAN_LIMIT = 600             # newest documents that are searched

STOP = {
    "the", "and", "for", "are", "was", "were", "what", "when", "where", "who", "how", "why",
    "does", "did", "has", "have", "will", "can", "you", "your", "our", "this", "that", "there",
    "about", "tell", "please", "any", "with", "from", "into", "than", "then", "its", "his",
    "her", "they", "them", "now", "today", "tomorrow", "know", "want", "need", "get", "give",
    "show", "list", "main", "history", "about", "background", "philippine", "philippines", "filipino", "time", "year", "years", "date",
    "day", "week", "month", "now", "latest", "new", "next", "upcoming", "currently", "news", "update",
    "updates", "nemsu", "campus", "tandag", "school", "university", "is", "in", "of", "to",
    "a", "an", "on", "at", "be", "me", "my", "it", "do", "i", "or", "by", "as",
    # common Filipino / Bisaya filler words
    "ang", "ng", "sa", "mga", "ba", "ko", "mo", "na", "pa", "po", "ano", "unsa", "kay",
    "naa", "nga", "ni", "si", "ug", "og", "para", "ito", "yung", "yang", "mag", "kung",
}


# Older syncs saved typographic marks as 'â€' + letters (and NFKC turned the trade-mark sign
# into the letters 'TM'). These are the usual ones; tidy() puts the real characters back.
_LEFTOVERS = [("\u00e2\u20acTM", "\u2019"), ("\u00e2\u20ac\u201c", "\u2013"),
              ("\u00e2\u20ac\u201d", "\u2014"), ("\u00e2\u20ac\u0153", "\u201c"),
              ("\u00e2\u20ac\u009d", "\u201d"), ("\u00e2\u20ac\u00a6", "\u2026"),
              ("\u00e2\u20ac\u02dc", "\u2018"), ("\u00e2\u20ac", "\u2019")]


def tidy(text):
    """Repair the leftovers above (safe on text that is already fine)."""
    for bad, good in _LEFTOVERS:
        text = (text or "").replace(bad, good)
    return text or ""


_ABBREVIATIONS = ("dr", "mr", "mrs", "ms", "sr", "jr", "hon", "atty", "engr", "prof", "no", "st",
                  "vs", "gen", "col", "dir", "asst", "assoc", "rep", "sen", "gov", "cong", "capt", "lt", "inc", "ph")


def cut_at_sentence(text, limit):
    """Shorten text to about `limit` characters, ending on a full sentence (not after 'Dr.')."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    best = -1
    for m in re.finditer(r"[.!?][\"')\]]?(?=\s)", cut):
        word = re.search(r"(\w+)\W*$", cut[:m.start()])
        if m.group(0).startswith(".") and word and word.group(1).lower() in _ABBREVIATIONS:
            continue
        if len(word.group(1) if word else "") == 1 and m.group(0).startswith("."):
            continue                                     # an initial such as 'Romeo S.'
        best = m.end()
    if best > limit // 3:
        return cut[:best].rstrip()
    return cut.rsplit(" ", 1)[0].rstrip() + "..."


def _stem(word):
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def keywords(question):
    """Meaningful words of a question (lower case, simple plural stripping)."""
    words = [w for w in normalize(question).split() if len(w) > 2 and w not in STOP]
    return list(dict.fromkeys(_stem(w) for w in words))


def _words(text):
    return {_stem(w) for w in normalize(text).split()}


def score(words, title, content, official=False):
    """(score, matched) for one document."""
    t, c = _words(title), _words(content)
    matched = [w for w in words if w in t or w in c]
    # a word in the title is worth 3, and 1 more if the body also has it; body only = 1
    points = sum((3 + (1 if w in c else 0)) if w in t else 1 for w in matched)
    ok = len(matched) >= 2 and points >= MIN_SCORE
    if official and ((matched and points >= PAGE_MIN_SCORE)      # "who is the president"
                     or len(matched) >= 2):                      # "who is the dean of cite"
        ok = True
    return (points if ok else 0), matched


def best_passage(content, words, limit=MAX_CHARS_PER_DOC):
    """The paragraphs of an article that mention most of the question's words."""
    parts = [p.strip() for p in tidy(content).split("\n") if p.strip()]
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
        official = r.get("source_type") == OFFICIAL
        points, matched = score(words, r["title"], r["content"], official)
        if points:
            hits.append((points, r["published_at"] or 0, r, matched))
    hits.sort(key=lambda h: (-h[0], -(h[1].timestamp() if h[1] else 0)))
    return [dict(h[2], score=h[0],
                 passage=best_passage(h[2]["content"], h[3],
                                      PAGE_CHARS_PER_DOC if h[2].get("source_type") == OFFICIAL
                                      else MAX_CHARS_PER_DOC))
            for h in hits[:limit]]


def _select():
    return select(KnowledgeDocument.title, KnowledgeDocument.content, KnowledgeDocument.source_url,
                  KnowledgeDocument.published_at, KnowledgeDocument.source_type)


def _as_dicts(result):
    return [dict(title=t, content=c, source_url=u, published_at=p, source_type=s)
            for t, c, u, p, s in result]


def _rows(db: Session, limit=SCAN_LIMIT, official=True):
    """Newest news/memos, plus (when official=True) ALL official website pages, which
    have no date and would otherwise fall off the end of a long newest-first list."""
    q = _select().where(KnowledgeDocument.source_type != OFFICIAL) \
        .order_by(KnowledgeDocument.published_at.desc().nullslast(),
                  KnowledgeDocument.id.desc()).limit(limit)
    rows = _as_dicts(db.execute(q))
    if official:
        pages = _select().where(KnowledgeDocument.source_type == OFFICIAL) \
            .order_by(KnowledgeDocument.id)
        rows += _as_dicts(db.execute(pages))
    return rows


def search(db: Session, question, limit=MAX_DOCS):
    return rank(_rows(db), question, limit)


def latest(db: Session, limit=3):
    return _rows(db, limit, official=False)               # "latest news" never lists pages


def _date(d):
    return d["published_at"].strftime("%b %d, %Y").replace(" 0", " ") if d.get("published_at") else ""


def for_prompt(docs):
    """Text block that goes into the AI's system prompt."""
    blocks = []
    for i, d in enumerate(docs, 1):
        blocks.append(f"[{i}] {tidy(d['title'])} ({_date(d) or 'no date'})\n{d['passage']}")
    return (
        "OFFICIAL NEMSU INFORMATION (NEMSU Newsroom articles and pages of the official NEMSU "
        "website). Answer the question ONLY from these sources. If they do not contain the "
        "answer, say you could not find it in the official NEMSU information. Never invent "
        "names, dates, positions or numbers.\n\n"
        + "\n\n".join(blocks))


def sources_text(docs):
    """Source lines added under the answer so students can open the full article."""
    lines = [f"- {tidy(d['title'])}" + (f" ({_date(d)})" if _date(d) else "") + f"\n  {d['source_url']}"
             for d in docs]
    return "Source" + ("s" if len(docs) > 1 else "") + ":\n" + "\n".join(lines)


def fallback_answer(docs):
    """Used when the language model is unavailable: show the best article directly."""
    d = docs[0]
    text = cut_at_sentence(d["passage"], 900)
    return f"Here is what I found in the official NEMSU information:\n\n{tidy(d['title'])}\n{text}"


def latest_text(docs):
    lines = [f"- {tidy(d['title'])}" + (f" ({_date(d)})" if _date(d) else "") + f"\n  {d['source_url']}"
             for d in docs]
    return "Latest from the NEMSU Newsroom:\n" + "\n".join(lines)


# ---- "give me the text / details of that news"
_DETAIL_WORDS = {"text", "content", "description", "details", "detail", "full", "summary",
                 "summarize", "summarise", "read", "explain", "more"}
_REF_WORDS = {"news", "article", "story", "post", "announcement", "that", "this", "it", "those"}


def wants_article_text(question):
    """True for follow-ups such as 'give me the text of that news' or 'give me the description'.
    The chatbot has no memory, so these are answered with the newest NEMSU article."""
    words = normalize(question).split()
    has_detail = any(w in _DETAIL_WORDS for w in words)
    has_ref = any(w in _REF_WORDS for w in words)
    return has_detail and (has_ref or len(words) <= 4)


def article_reply(doc, limit=1500):
    """The article text (cut at the end of a sentence) with a link to the full article."""
    text = cut_at_sentence(tidy(doc.get("content")).strip(), limit)
    date = f" ({_date(doc)})" if _date(doc) else ""
    return f"{tidy(doc['title'])}{date}\n\n{text}\n\nFull article:\n{doc['source_url']}"