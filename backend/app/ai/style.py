"""Add an occasional, context-aware emoji to friendly replies."""

import re
import zlib

from app.ai import texts
from app.services import sentiment_service

ALLOWED = ("😊", "🥳", "😂", "😁", "❤️", "👍", "😉", "😎", "😢", "😅", "😄", "😃",
           "😋", "🥰", "🤔", "🤗", "🙂", "😑", "😮", "☠️", "🧠", "⚡", "😵‍💫", "🥶")
EMOJI = re.compile("|".join(re.escape(emoji) for emoji in sorted(ALLOWED, key=len, reverse=True)))
PREFERRED = ("😊", "🙂", "😄", "😃", "😁", "😉", "😅", "🥳", "😂", "🥰", "🤗",
             "😎", "😋", "👍", "❤️", "🤔", "😮", "😢", "😑", "☠️", "🧠", "⚡", "😵‍💫", "🥶")


def _best(emojis):
    """Prefer a warm expression when mirroring one of the user's approved emojis."""
    found = [emoji for emoji in emojis if emoji in PREFERRED]
    return min(found, key=PREFERRED.index) if found else None


CASUAL = {"haha", "hahaha", "hehe", "hihi", "lol", "lmao", "omg", "yay", "wow", "pls", "plss", "plz",
          "please", "thanks", "thank", "salamat", "ty", "charot", "nice", "daghang", "maraming",
          "palihug", "paki"}
_WORD = re.compile(r"[a-z']+")
MAX_LENGTH = 600
TONE_EMOJI = {
    "curious": "🤔", "wonder": "🤔", "wondering": "🤔", "question": "🤔",
    "confused": "😅", "confusing": "😅", "unsure": "😅", "understand": "🤔",
    "happy": "😊", "excited": "🥳", "celebrate": "🥳", "love": "🥰",
    "funny": "😂", "laugh": "😂", "sad": "😢", "cold": "🥶", "surprised": "😮",
}


def _friendly(question):
    lowered = question.lower()
    words = set(_WORD.findall(lowered))
    return bool(words & CASUAL) or ":)" in question or ":D" in question or "!!" in question \
        or "^_^" in question


def _tone_emoji(question):
    """Choose an emoji when wording clearly signals curiosity or emotion."""
    if sentiment_service.analyze(question)["label"] == "Negative":
        return None
    words = set(_WORD.findall(question.lower()))
    for tone in ("confused", "confusing", "unsure", "curious", "wondering", "wonder",
                 "surprised", "excited", "happy", "love", "funny", "laugh", "sad", "cold"):
        if tone in words:
            return TONE_EMOJI[tone]
    return None


def _roll(question):
    """Keep casual-message behavior consistent for a given input."""
    return zlib.crc32(question.strip().lower().encode("utf-8")) % 2 == 0


def add_emoji(result, question):
    answer = result.get("answer")
    key = texts.key_of(answer)
    if (not isinstance(answer, str) or result.get("type") not in ("message", "map")
            or key in texts.SERIOUS or len(answer) > MAX_LENGTH or result.get("serious")
            or EMOJI.search(answer)):
        result.pop("serious", None)
        return result
    result.pop("serious", None)

    theirs = EMOJI.findall(question)
    tone_emoji = _tone_emoji(question)
    if not theirs and not tone_emoji and not (_friendly(question) and _roll(question)):
        return result
    if sentiment_service.analyze(question)["label"] == "Negative":
        return result

    canned = texts.FRIENDLY_EMOJI.get(key)
    if canned not in ALLOWED:
        canned = None
    emoji = _best(theirs) or tone_emoji or canned or "🙂"
    first, sep, rest = answer.partition("\n\n")
    result["answer"] = f"{first.rstrip()} {emoji}{sep}{rest}"
    return result
