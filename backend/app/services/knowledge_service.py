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
from difflib import SequenceMatcher
from urllib.parse import urlsplit

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
    "show", "list", "main", "many", "much", "number", "total", "count", "history", "about", "background", "philippine", "philippines", "filipino", "time", "year", "years", "date",
    "day", "week", "month", "now", "latest", "new", "next", "upcoming", "currently", "news", "update",
    "updates", "nemsu", "campus", "tandag", "school", "university", "is", "in", "of", "to",
    "a", "an", "on", "at", "be", "me", "my", "it", "do", "i", "or", "by", "as",
    # common Filipino / Bisaya filler words
    "ang", "ng", "sa", "mga", "ba", "ko", "mo", "na", "pa", "po", "ano", "unsa", "kay",
    "naa", "nga", "ni", "si", "ug", "og", "para", "ito", "yung", "yang", "mag", "kung",
}

# Common ways students refer to the same kinds of official NEMSU information.
# Expand only when a query contains one of these terms so ordinary searches stay precise.
_QUERY_SYNONYMS = {
    "achievement": {"accomplishment", "award", "recognition", "honor", "honour", "distinction"},
    "accomplishment": {"achievement", "award", "recognition", "honor", "honour", "distinction"},
    "award": {"achievement", "accomplishment", "recognition", "honor", "honour", "distinction"},
    "recognition": {"achievement", "accomplishment", "award", "honor", "honour", "distinction"},
    "profile": {"biography", "bio", "background", "career", "education"},
    "biography": {"profile", "bio", "background", "career", "education"},
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


def _matches(query_word, text_words):
    variants = {query_word, *_QUERY_SYNONYMS.get(query_word, ())}
    return variants & text_words


def _words(text):
    return {_stem(w) for w in normalize(text).split()}


def score(words, title, content, official=False):
    """(score, matched) for one document."""
    t, c = _words(title), _words(content)
    matched = [w for w in words if _matches(w, t | c)]
    # a word in the title is worth 3, and 1 more if the body also has it; body only = 1
    points = sum((3 + (1 if _matches(w, c) else 0)) if _matches(w, t) else 1
                 for w in matched)
    ok = len(matched) >= 2 and points >= MIN_SCORE
    if official and ((matched and points >= PAGE_MIN_SCORE)      # "who is the president"
                     or len(matched) >= 2):                      # "who is the dean of cite"
        ok = True
    return (points if ok else 0), matched


def best_passage(content, words, limit=MAX_CHARS_PER_DOC):
    """Select matching lines with nearby context, preserving names, roles, and headings."""
    parts = [p.strip() for p in tidy(content).split("\n") if p.strip()]
    if not parts:
        return ""
    if sum(len(p) for p in parts) <= limit:
        return "\n".join(parts)
    scores = [sum(1 for w in words if _matches(w, _words(part))) for part in parts]
    # A matching line often contains only a person's name or a label; the fact itself
    # (position, award, or explanation) is on the next line. Grow a small window around
    # each match so the model receives that evidence together.
    ranked = sorted((i for i, value in enumerate(scores) if value),
                    key=lambda i: (-scores[i], i))
    selected = set()
    for i in ranked:
        window = range(max(0, i - 1), min(len(parts), i + 3))
        added = [j for j in window if j not in selected]
        if not added:
            continue
        size = sum(len(parts[j]) + 1 for j in added)
        current = sum(len(parts[j]) + 1 for j in selected)
        if current + size <= limit:
            selected.update(added)
        elif not selected:
            parts[i] = parts[i][:max(1, limit - 1)]
            selected.add(i)
            break
    if not selected:
        return ""
    return "\n".join(parts[i] for i in sorted(selected))


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


_CAMPUS_SLUGS = {
    "tandag": "Tandag", "bislig": "Bislig", "cantilan": "Cantilan",
    "tagbina": "Tagbina", "lianga": "Lianga", "san-miguel": "San Miguel",
    "cagwait": "Cagwait",
}


def campus_program_pages(db):
    """Return official campus pages narrowed to their complete program-offering sections."""
    pages = []
    for row in _rows(db, official=True):
        if row.get("source_type") != OFFICIAL:
            continue
        match = re.fullmatch(r"/campuses/([a-z-]+)/?", urlsplit(row.get("source_url", "")).path)
        if not match or match.group(1) not in _CAMPUS_SLUGS:
            continue
        lines = tidy(row.get("content", "")).splitlines()
        start = next((i for i, line in enumerate(lines)
                      if normalize(line).strip() == "program offerings"), None)
        if start is None:
            continue
        end = next((i for i in range(start + 1, len(lines))
                    if normalize(lines[i]).strip() in {
                        "facilities", "services", "spaces for learning research and service",
                        "student experiences beyond the classroom", "updates",
                    }), len(lines))
        # Older syncs sometimes flattened prospectus links from college pages
        # into a campus page (for example, "Course: programs/BSCS.pdf"). Those
        # link labels are not campus-specific offerings, so don't expose them
        # as evidence for a campus list.
        section_lines = []
        for line in lines[start:end]:
            clean = line.strip()
            if not clean or re.search(r"(?:^|\s|:)programs?/[^\s]+\.pdf\b", clean, re.I):
                continue
            section_lines.append(clean)
        # Campus pages publish program lists under counted college headings,
        # such as "College of Business and Management 3 programs". Older
        # polluted syncs contain only site-navigation labels like "College of
        # Law" followed by unrelated links; reject those sections wholesale.
        if not any(re.fullmatch(r"College of .+?\s+\d+\s+programs?", line, re.I)
                   for line in section_lines):
            continue
        section = "\n".join(section_lines)
        if len(section) < 40:
            continue
        campus = _CAMPUS_SLUGS[match.group(1)]
        pages.append({**row, "title": f"{campus} Campus program offerings",
                      "content": section, "passage": section, "campus": campus})
    return pages


_PROGRAM_FILLER = {"bachelor", "bachelors", "degree", "program", "course", "major", "in", "of",
                   "the", "at", "and", "bs", "bsc", "ba", "bachelor's", "what", "where",
                   "is", "are", "does", "do", "or", "here", "there", "located", "location",
                   "offer", "offered", "available", "availability",
                   "campus", "campuses", "main", "tandag", "bislig", "cantilan", "tagbina",
                   "lianga", "cagwait", "san", "miguel", "nemsu", "north", "eastern",
                   "mindanao", "state", "university"}
_CAMPUS_NAMES = ("San Miguel", "Tandag", "Bislig", "Cantilan", "Tagbina", "Lianga", "Cagwait")


def _program_terms(text):
    return [w for w in normalize(text).split() if w not in _PROGRAM_FILLER]


def _program_matches(requested, listed):
    wanted = _program_terms(requested)
    available = set(normalize(listed).split())
    return bool(wanted) and all(any(word == candidate or
                                    (len(word) >= 4 and candidate.startswith(word))
                                    or (len(word) >= 5 and SequenceMatcher(None, word, candidate).ratio() >= .78)
                                    or (word.endswith("y") and word[:-1] + "ies" == candidate)
                                    for candidate in available) for word in wanted)


def resolve_program_name(db, requested):
    """Return the official program label that best matches a possibly misspelled name."""
    requested_terms = _program_terms(requested)
    if not requested_terms:
        return requested
    candidates = []
    for row in _rows(db, official=True):
        if row.get("source_type") != OFFICIAL:
            continue
        lines = [line.strip() for line in tidy(row.get("content", "")).splitlines() if line.strip()]
        for index, line in enumerate(lines):
            offered = re.search(r"\bOffered at\s*(.*)$", line, re.I)
            if not offered:
                continue
            label = line[:offered.start()].strip(" -:â€¢")
            if not label and index:
                label = lines[index - 1].strip(" -:â€¢")
            if label and _program_matches(requested, label):
                # Prefer a title whose meaningful tokens closely match the requested name.
                wanted = " ".join(requested_terms)
                terms = " ".join(_program_terms(label))
                score = SequenceMatcher(None, wanted, terms).ratio()
                candidates.append((score, label))
    return max(candidates, default=(0, requested))[1]


def program_offerings(db, program):
    """Find explicit program-to-campus mappings and entries in official campus lists.

    Returns the listed campuses, sources, and completeness information for a grounded
    answer about whether the course appears in Tandag's official list.
    """
    program = resolve_program_name(db, program)
    sources = []
    offered = set()
    has_college_mapping = False
    for row in _rows(db, official=True):
        if row.get("source_type") != OFFICIAL:
            continue
        lines = [line.strip() for line in tidy(row.get("content", "")).splitlines() if line.strip()]
        for index, line in enumerate(lines):
            found = re.search(r"\bOffered at\s*(.*)$", line, re.I)
            if not found:
                continue
            offered_text = found.group(1)
            program_label = line[:found.start()].strip(" -:•")
            if not program_label and index:
                program_label = lines[index - 1].strip(" -:•")
            if not offered_text and index + 1 < len(lines):
                offered_text = lines[index + 1]
            if not _program_matches(program, program_label):
                continue
            campuses = {name for name in _CAMPUS_NAMES
                        if re.search(rf"\b{re.escape(name)}\s+Campus\b", offered_text, re.I)}
            if campuses:
                has_college_mapping = True
                offered.update(campuses)
                sources.append(dict(row, passage=line))

    campus_pages = campus_program_pages(db)
    for page in campus_pages:
        offering_lines = [line for line in page["content"].splitlines()
                          if line.strip() and not normalize(line).startswith("college of")]
        if any(_program_matches(program, line) for line in offering_lines):
            offered.add(page["campus"])
            sources.append(dict(page, passage=page["content"]))
    tandag_page = next((page for page in campus_pages if page["campus"] == "Tandag"), None)
    specific = bool(_program_terms(program))
    if specific and tandag_page:
        sources.append(dict(tandag_page, passage=tandag_page["content"]))
    # Deduplicate page sources when a college offering line and campus listing share a URL.
    unique = {}
    for source in sources:
        unique[source["source_url"]] = source
    return {
        "program": program,
        "campuses": sorted(offered),
        "sources": list(unique.values()),
        "college_mapping": has_college_mapping,
        "campus_pages": sorted(page["campus"] for page in campus_pages),
        "campus_lists_complete": len(campus_pages) == len(_CAMPUS_SLUGS),
        "specific_program": specific,
    }


def search(db: Session, question, limit=MAX_DOCS):
    return rank(_rows(db), question, limit)


def directory_lookup(db: Session, question):
    """Find an explicitly listed person from the official Directory table."""
    query_terms = set(keywords(question))
    query_terms.discard("mean")  # conversational correction: "I mean, who is..."
    if not query_terms:
        return None
    candidates = []
    for row in _rows(db, official=True):
        if row.get("source_type") != OFFICIAL or urlsplit(row.get("source_url", "")).path.rstrip("/") != "/directory":
            continue
        lines = [line.strip() for line in tidy(row.get("content", "")).splitlines() if line.strip()]
        records = []
        for line in lines:
            columns = [part.strip() for part in line.split("|")]
            if len(columns) >= 2:
                records.append(columns)
        # Older syncs stored table cells on separate lines. Read the four-column
        # directory rows in order as a fallback until the page is synced again.
        if not records:
            for index, line in enumerate(lines):
                if normalize(line) != "name" or index + 4 >= len(lines):
                    continue
                header = [normalize(value) for value in lines[index:index + 4]]
                if header != ["name", "office designation", "contact number", "email address"]:
                    continue
                cursor = index + 4
                while cursor + 3 < len(lines):
                    values = lines[cursor:cursor + 4]
                    if normalize(values[0]) in {"other university wide designations", "latest news", "name"}:
                        break
                    records.append(values)
                    cursor += 4
        for columns in records:
            if len(columns) < 2 or normalize(columns[0]) in {"name", "directory listings"}:
                continue
            name, designation = columns[0], columns[1]
            if len(name.split()) < 2 or len(designation.split()) < 2:
                continue
            role_hits = query_terms & set(keywords(designation))
            name_hits = query_terms & set(keywords(name))
            # Require a clear match to the role or to a multiword name. This keeps
            # generic questions like "who is the president?" out of this lookup.
            if len(role_hits) >= 2 or len(name_hits) >= 2:
                candidates.append((len(role_hits) * 2 + len(name_hits), len(role_hits),
                                   name, designation, columns, row))
    if not candidates:
        return None
    if query_terms == {"vice", "president"}:
        vice_presidents = [item for item in candidates
                           if {"vice", "president"} <= set(keywords(item[3]))]
        unique = {}
        for item in vice_presidents:
            unique[item[2]] = {"name": item[2], "designation": item[3],
                               "email": next((part for part in item[4][2:] if "@" in part), None)}
        if unique:
            return {"matches": list(unique.values()), "source_url": vice_presidents[0][5]["source_url"]}
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best = candidates[0]
    if len(candidates) > 1 and candidates[1][:2] == best[:2]:
        return None
    email = next((part for part in best[4][2:] if "@" in part), None)
    return {"name": best[2], "designation": best[3], "email": email,
            "source_url": best[5]["source_url"]}


def latest(db: Session, limit=3):
    return _rows(db, limit, official=False)               # "latest news" never lists pages


def _date(d):
    return d["published_at"].strftime("%b %d, %Y").replace(" 0", " ") if d.get("published_at") else ""


def for_prompt(docs, education=False):
    """Text block that goes into the AI's system prompt."""
    blocks = []
    for i, d in enumerate(docs, 1):
        blocks.append(f"[{i}] {tidy(d['title'])} ({_date(d) or 'no date'})\n{d['passage']}")
    if education:
        instruction = (
            "OFFICIAL NEMSU INFORMATION. Use these sources for claims about NEMSU offerings. "
            "When teaching the academic subject, you may add clearly labeled general educational "
            "background, but do not present it as NEMSU's curriculum. Never invent NEMSU-specific "
            "names, dates, positions, requirements, or numbers.\n\n")
    else:
        instruction = (
            "OFFICIAL NEMSU INFORMATION (NEMSU Newsroom articles and pages of the official NEMSU "
            "website). Answer the question ONLY from these sources. If they do not contain the "
            "answer, say you could not find it in the official NEMSU information. Never invent "
            "names, dates, positions or numbers.\n\n")
    return instruction + "\n\n".join(blocks)


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

_QUANTITY = re.compile(r"\b(how many|how much|number of|total number|how large)\b", re.I)


def wants_number(question):
    """'How many faculty?' needs a figure; an article without any digit cannot answer it."""
    return bool(_QUANTITY.search(question or ""))


def with_figures(docs):
    """Keep only the documents whose passage contains a number."""
    return [d for d in docs if re.search(r"\d", d.get("passage", ""))]
