"""
ai/language.py - understanding the language the person writes in.

* English, Tagalog (Filipino) and Bisaya (Cebuano), also mixed ("Taglish", "Bislish"):
  the rules understand common words of all three and the fixed replies are sent back
  in the same language (ai/texts.py). The language model is told to answer in it too.
* Any other language (Spanish, Chinese, Korean, ...): the question is translated to
  English by the language model, answered, and the answer is translated back.
"""

import re

from app.ai import texts

# words that only (or mostly) one language uses; shared words (wala, nga, ba, pwede, ...) are left out
BISAYA = {
    "unsa", "asa", "kinsa", "ngano", "unsaon", "pila", "naa", "naay", "dili", "ug", "kaayo",
    "gyud", "ni", "kini", "kana", "kadto", "diri", "didto", "dapit", "imong", "atong", "among",
    "nimo", "nako", "kasabot", "kasabut", "makasabot", "palihug", "daghang", "maayong", "buntag",
    "gabii", "adlaw", "lagi", "ra", "tabang", "tabangi", "pangita", "gipangita", "akoa", "imoha",
    "abri", "abli", "abre", "run", "ron", "karon", "kanus", "unsay", "kinsay", "gani", "pud",
    "usab", "pag", "mao", "murag", "lagot", "gamay", "dako", "kuyaw", "sirado", "gikan", "adto",
    "moadto", "musta", "makita", "nakit", "kabalo", "tagpila", "oy", "bitaw", "diay", "bay", "dong",
    "day", "ayaw", "makig", "amigo", "makiamigo", "mag-amigo", "kauban", "higala", "wa", "mi", "nato", "ato", "ila", "ilang", "niya", "siya", "sila", "mga",
}
TAGALOG = {
    "ano", "saan", "sino", "bakit", "paano", "kailan", "magkano", "nasaan", "hindi", "ako",
    "ikaw", "kami", "tayo", "kayo", "ito", "iyan", "iyon", "yan", "yun", "po", "opo", "ng",
    "paki", "pakiusap", "maraming", "kumusta", "kamusta", "magandang", "umaga", "hapon",
    "naman", "din", "rin", "may", "mayroon", "kasi", "pero", "tulong", "tulungan", "hanap",
    "hanapin", "hinahanap", "bukas", "sarado", "ngayon", "dito", "doon", "diyan", "mo", "ko",
    "natin", "namin", "nila", "niya", "kita", "lang", "talaga", "sana", "naiintindihan",
    "marunong", "wika", "kaibigan", "makipagkaibigan", "patulong", "magkaibigan", "aking", "iyong", "inyong", "nito", "niyan", "nun", "pwedeng",
}
# these overlap with the other language so they carry no weight
_SHARED = {"mga", "siya", "niya", "sila", "wa", "mi", "ko", "mo"}
BISAYA -= _SHARED
TAGALOG -= _SHARED

# Tagalog AND Bisaya use these, so alone they only say "not English"
LOCAL = {"pede", "pwede", "nawala", "akong", "akoang", "wala", "nga", "ba", "pwede", "salamat", "para", "ang", "sa",
         "na", "po", "pa", "nawalan", "gikawat", "ninakaw", "nakawan", "naiwan", "nakalimtan"}

ENGLISH = {
    "the", "is", "are", "what", "where", "how", "can", "you", "my", "i", "a", "an", "to", "of",
    "and", "in", "for", "do", "does", "this", "that", "it", "me", "please", "when", "who",
    "why", "which", "there", "have", "has", "need", "want", "help", "find", "show", "about",
    "with", "on", "at", "your", "we", "they", "be", "was", "will", "would", "could",
}
SPANISH = {"hola", "donde", "dónde", "está", "estan", "gracias", "quiero", "puedo", "cómo", "como",
           "qué", "que", "por", "favor", "necesito", "biblioteca", "cuándo", "tengo", "buenos",
           "días", "dias", "ayuda", "universidad", "escuela", "sala", "y", "el", "la", "los", "las",
           "dónde", "esta", "una", "un", "mi", "tu", "es", "son", "puede", "puedes"}
_WORD = re.compile(r"[^\W\d_']+(?:'[^\W\d_]+)?", re.UNICODE)


def detect(text):
    """'en', 'tl' (Tagalog), 'ceb' (Bisaya) or 'other'."""
    words = [w.lower() for w in _WORD.findall(text or "")]
    if not words:
        return "en"
    letters = [c for c in (text or "") if c.isalpha()]
    if letters and sum(1 for c in letters if ord(c) > 0x24F) / len(letters) > 0.3:
        return "other"                                   # Chinese, Korean, Arabic, Russian, ...
    ceb = sum(1 for w in words if w in BISAYA)
    tl = sum(1 for w in words if w in TAGALOG)
    en = sum(1 for w in words if w in ENGLISH)
    es = sum(1 for w in words if w in SPANISH and w not in ENGLISH)
    if es >= 2 and es > en and es > ceb + tl:
        return "other"                                   # Spanish
    local = sum(1 for w in words if w in LOCAL)
    if ceb + tl == 0:
        return "ceb" if local and not en else "en"      # e.g. "nawala akong phone"
    if en > ceb + tl:
        return "en"
    if ceb == tl:
        return "ceb"                                     # Tandag is Bisaya-speaking
    return "ceb" if ceb > tl else "tl"


def localize(result, lang):
    """Swap the English fixed reply for its Tagalog / Bisaya version."""
    if lang in ("tl", "ceb") and isinstance(result.get("answer"), str):
        translated = texts.translate(result["answer"], lang)
        if translated:
            result["answer"] = translated
    return result


# ------------------------------------------------- any other language: via the model
TO_ENGLISH = ("Translate the user's message into English. It is a question to a university campus "
              "assistant. Output ONLY the English translation, nothing else. Keep names, room "
              "codes and acronyms unchanged.")
FROM_ENGLISH = ("Translate the following chat reply into the same language as this person's "
                "message: \"{sample}\". Keep names, room codes, acronyms, numbers, line breaks, "
                "URLs and markdown links exactly as they are. Output ONLY the translation.")
MAX_TRANSLATE = 1500


def to_english(question, ask):
    try:
        english = ask(TO_ENGLISH, question)
    except Exception:
        english = None
    return (english or "").strip() or None


def from_english(result, question, ask):
    answer = result.get("answer")
    if not isinstance(answer, str) or not answer or len(answer) > MAX_TRANSLATE:
        return result
    try:
        translated = ask(FROM_ENGLISH.format(sample=question[:120].replace('"', "'")), answer)
    except Exception:
        translated = None
    if translated and translated.strip():
        result["answer"] = translated.strip()
    return result
