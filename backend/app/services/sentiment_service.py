"""
services/sentiment_service.py - AI sentiment analysis for feedback, concerns and reports.

Approach: rule-based (lexicon) NLP. It runs instantly, needs no API key and no
internet, and always gives the same answer for the same text.

What it understands
  * English, Filipino/Tagalog and Bisaya words and phrases ("salamat", "pangit", "guba")
  * negation:   "not good" -> negative, "not bad" -> positive, "no problem" -> positive
  * intensity:  "very slow", "sobrang init", "grabe", "kaayo"
  * contrast:   "The staff are kind but the room is dirty" -> the part after "but" counts more
  * emojis

Result:  {"label": "Positive" | "Neutral" | "Negative" | "Mixed", "score": -100..100}
Only administrators see it. Add words to the lists below to teach it more.
"""

import re

from sqlalchemy import select, update
from sqlalchemy.orm import Session

LABELS = ("Positive", "Neutral", "Negative", "Mixed")

# --------------------------------------------------------------- lexicon
POSITIVE = {
    # English
    "good": 1, "great": 1.5, "excellent": 2, "amazing": 2, "awesome": 2, "wonderful": 2,
    "fantastic": 2, "perfect": 2, "love": 1.5, "like": 0.7, "nice": 1, "clean": 1,
    "helpful": 1.5, "friendly": 1.2, "kind": 1, "fast": 1, "quick": 1, "easy": 1,
    "comfortable": 1.2, "happy": 1.5, "satisfied": 1.5, "thank": 1, "thanks": 1,
    "appreciate": 1.5, "appreciated": 1.5, "best": 1.5, "better": 0.8, "improved": 1,
    "well": 0.6, "smooth": 1, "organized": 1, "accommodating": 1.5, "recommend": 1.2,
    "safe": 1, "working": 0.5, "resolved": 1, "fixed": 1, "impressed": 1.5, "enjoy": 1.2,
    "approachable": 1.2, "convenient": 1, "spacious": 1, "cool": 0.6, "okay": 0.3,
    "thank you": 1.5, "good job": 2, "well done": 2, "keep it up": 1.5,
    # Filipino / Tagalog
    "salamat": 1.2, "maraming salamat": 1.8, "maganda": 1.2, "mabuti": 1, "ayos": 1,
    "galing": 1.5, "mahusay": 1.5, "mabait": 1.2, "malinis": 1.2, "masaya": 1.5,
    "maayos": 1.2, "magaling": 1.5, "gusto": 0.8, "mabilis": 1, "angkop": 0.5,
    # Bisaya
    "maayo": 1.2, "nindot": 1.3, "daghang salamat": 1.8, "limpyo": 1.2, "lingaw": 1.2,
    "salamat kaayo": 1.8, "buotan": 1.2, "paspas": 1, "sayon": 0.8,
    "👍": 1.5, "😊": 1.2, "😍": 1.5, "❤": 1.5, "🙏": 0.8, "👏": 1.5, "😀": 1,
}
NEGATIVE = {
    # English
    "bad": 1.2, "poor": 1.2, "terrible": 2, "awful": 2, "horrible": 2, "worst": 2.2,
    "hate": 1.8, "dirty": 1.3, "slow": 1.1, "broken": 1.5, "damaged": 1.4, "leaking": 1.2,
    "leak": 1.1, "unsafe": 1.6, "dangerous": 1.7, "rude": 1.7, "unhelpful": 1.6,
    "disappointed": 1.7, "disappointing": 1.7, "angry": 1.6, "annoying": 1.4, "problem": 1,
    "issue": 0.7, "complaint": 1, "complain": 1.1, "delay": 1, "delayed": 1.1, "late": 0.6,
    "noisy": 1, "smelly": 1.3, "stinks": 1.4, "hot": 0.5, "uncomfortable": 1.2, "crowded": 0.8,
    "difficult": 0.9, "confusing": 1, "waste": 1.2, "useless": 1.7, "unacceptable": 1.8,
    "frustrating": 1.6, "frustrated": 1.6, "fail": 1.2, "failed": 1.2, "failure": 1.3,
    "lack": 0.8, "lacking": 0.9, "missing": 0.8, "stolen": 1.4, "lost": 0.6, "unfair": 1.5,
    "harassment": 2, "bullying": 2, "neglect": 1.6, "ignored": 1.4, "cracked": 1.2, "faulty": 1.4,
    "out of order": 1.5, "not working": 1.5, "does not work": 1.5, "doesn't work": 1.5,
    "not function": 1.4, "no water": 1.3, "no wifi": 1.2, "no internet": 1.2, "no signal": 1.1,
    "no electricity": 1.3, "no light": 1.1, "no aircon": 1.0, "walang tubig": 1.3,
    "walay tubig": 1.3, "walang kuryente": 1.3, "walay kuryente": 1.3,
    # Filipino / Tagalog
    "pangit": 1.4, "sira": 1.4, "basura": 1.3, "bulok": 1.5, "kalat": 1.2, "madumi": 1.3,
    "marumi": 1.3, "baho": 1.3, "mabaho": 1.3, "hirap": 1, "mahirap": 1, "matagal": 1,
    "bastos": 1.7, "reklamo": 1, "galit": 1.5, "inis": 1.3, "nakakainis": 1.5, "badtrip": 1.5,
    "nakakadismaya": 1.7, "walang": 0.9, "kulang": 1, "delikado": 1.5, "ingay": 1, "maingay": 1,
    "mainit": 0.6, "tumutulo": 1.1, "nawala": 0.7, "ninakaw": 1.5, "pabaya": 1.5,
    # Bisaya
    "guba": 1.4, "dugyot": 1.4, "mabaho kaayo": 1.8, "lisud": 1, "kuyaw": 1.5, "walay": 0.9,
    "ulaw": 0.8, "dili maayo": 1.3, "wala mi": 0.8, "hinay": 0.9, "lagot": 1.2, "bati": 1.3,
    "yagpis": 0.6, "nasuko": 1.3,
    "👎": 1.5, "😡": 1.8, "😠": 1.6, "😞": 1.2, "😢": 1.2, "😤": 1.3, "🤬": 2,
}
NEGATIONS = {"not", "no", "never", "cannot", "cant", "can't", "dont", "don't", "didnt", "didn't",
             "isnt", "isn't", "wasnt", "wasn't", "wont", "won't", "without", "hindi", "di",
             "dili", "wala", "ayaw", "hnd", "d", "dili"}
INTENSIFIERS = {"very": 1.5, "so": 1.3, "really": 1.4, "extremely": 1.8, "super": 1.5,
                "too": 1.3, "sobra": 1.6, "sobrang": 1.6, "grabe": 1.6, "talaga": 1.3,
                "totally": 1.5, "absolutely": 1.6, "labi": 1.5, "pinaka": 1.5, "very very": 1.8}
AFTER_INTENSIFIERS = {"kaayo": 1.5, "talaga": 1.3, "gyud": 1.4, "grabe": 1.5, "naman": 1.1, "po": 1.0}
CONTRAST = {"but", "however", "although", "though", "pero", "ngunit", "subalit", "apan",
            "kaso", "bisan"}
_WORD = re.compile(r"[a-z']+|[^\sa-z0-9']", re.IGNORECASE)    # words, and single symbols (emojis)
MAX_PHRASE = 3


def _tokens(text):
    return [t.lower() for t in _WORD.findall(text or "")]


def _lookup(tokens, i):
    """Longest phrase starting at i: returns (weight, length) or None. weight>0 positive."""
    for n in range(min(MAX_PHRASE, len(tokens) - i), 0, -1):
        phrase = " ".join(tokens[i:i + n])
        if phrase in NEGATIVE:
            return -NEGATIVE[phrase], n
        if phrase in POSITIVE:
            return POSITIVE[phrase], n
    return None


def analyze(text):
    """Returns {"label": ..., "score": -100..100} for any text."""
    tokens = _tokens(text)
    last_contrast = max((i for i, t in enumerate(tokens) if t in CONTRAST), default=-1)
    pos = neg = 0.0
    i = 0
    while i < len(tokens):
        hit = _lookup(tokens, i)
        if hit is None:
            i += 1
            continue
        weight, length = hit
        # intensity before / after the word
        if i > 0 and tokens[i - 1] in INTENSIFIERS:
            weight *= INTENSIFIERS[tokens[i - 1]]
        nxt = tokens[i + length] if i + length < len(tokens) else ""
        if nxt in AFTER_INTENSIFIERS:
            weight *= AFTER_INTENSIFIERS[nxt]
        # negation in the 3 words before ("not good", "hindi maganda", "no problem")
        window = tokens[max(0, i - 3):i]
        if any(w in NEGATIONS for w in window) and not any(w in CONTRAST for w in window):
            weight = -weight * 0.8
        # the idea after "but" is what the person really means
        if last_contrast >= 0:
            weight *= 1.5 if i > last_contrast else 0.6
        if weight > 0:
            pos += weight
        else:
            neg += -weight
        i += length

    net = pos - neg
    total = pos + neg
    score = round(100 * net / (total + 1))
    if pos >= 1 and neg >= 1 and min(pos, neg) / max(pos, neg) >= 0.6:
        label = "Mixed"
    elif net >= 0.75:
        label = "Positive"
    elif net <= -0.75:
        label = "Negative"
    else:
        label = "Neutral"
    return {"label": label, "score": max(-100, min(100, score))}


# ------------------------------------------------------- start-up backfill
def backfill(db: Session):
    """Give a sentiment to rows saved before this feature existed (runs once, quickly)."""
    from app.models import Concern, Feedback, Report
    for model, field in ((Concern, "description"), (Report, "description"), (Feedback, "message")):
        rows = db.execute(select(model.id, getattr(model, field)).where(model.sentiment.is_(None))).all()
        for row_id, text in rows:
            result = analyze(text)
            db.execute(update(model).where(model.id == row_id)
                       .values(sentiment=result["label"], sentiment_score=result["score"]))
    db.commit()
