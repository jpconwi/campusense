"""
ai/style.py - friendly emojis, only sometimes.

NEMSAI adds one emoji to a reply only when the person's own message is friendly:
  * they used an emoji themselves          -> always (it mirrors theirs when it is a happy one)
  * they sound casual ("haha", "thanks", "salamat", "pls", "!!", ":)") -> about every other time
Never in serious replies (refusals, lost items, concerns, forms, records, admin data) and
never when the person sounds upset.
"""

import re
import zlib

from app.ai import texts
from app.services import sentiment_service

EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2764]")
HAPPY = set("😀😃😄😁😆😊🙂😉😍🥰😘👍👏🙏❤🎉✨😎🤗😅😂🤣")
CASUAL = {"haha", "hahaha", "hehe", "hihi", "lol", "lmao", "omg", "yay", "wow", "pls", "plss", "plz",
          "please", "thanks", "thank", "salamat", "ty", "charot", "nice", "daghang", "maraming",
          "palihug", "paki"}
_WORD = re.compile(r"[a-z']+")
MAX_LENGTH = 600                      # long answers (lists, news, records) stay plain


def _friendly(question):
    lowered = question.lower()
    words = set(_WORD.findall(lowered))
    return bool(words & CASUAL) or ":)" in question or ":D" in question or "!!" in question \
        or "^_^" in question


def _roll(question):
    """The same message always gives the same 'sometimes' answer (no flicker, easy to test)."""
    return zlib.crc32(question.strip().lower().encode("utf-8")) % 2 == 0


def _default_emoji(result):
    if result.get("type") == "map":
        return "📍"
    return "🙂"


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
    if not theirs and not (_friendly(question) and _roll(question)):
        return result
    if sentiment_service.analyze(question)["label"] == "Negative":
        return result

    emoji = texts.FRIENDLY_EMOJI.get(key) or (
        next((e for e in theirs if e in HAPPY), None) or _default_emoji(result))
    if theirs and (key is None or key not in texts.FRIENDLY_EMOJI):
        emoji = next((e for e in theirs if e in HAPPY), emoji)
    first, sep, rest = answer.partition("\n\n")
    result["answer"] = f"{first.rstrip()} {emoji}{sep}{rest}"
    return result
