"""
ai/understand.py - the part of NEMSAI that "gets" what a person means.

The fast rules (ai/intent.py) answer common questions instantly. When they do not recognise a
message - slang, typos, mixed Bisaya/Tagalog/English, emojis, "can I ask something?" - the
language model first works out WHAT THE PERSON WANTS:

    {"kind": "campus" | "smalltalk" | "offtopic", "english": "<clear English version>"}

  campus     -> the clear English question goes back through the normal engine (forms, records,
                locations ... all still use the safe, rule-based code)
  smalltalk  -> a short friendly reply in the person's language, then an offer to help
  offtopic   -> the polite campus-only refusal

Earlier questions of the same chat are given too, so "and the canteen?" or "where is it?" work.
"""

import json
import re

REWRITE_PROMPT = """You help a university campus chatbot understand messages. The campus is NEMSU
Tandag Main Campus (Tandag City, Surigao del Sur, Philippines). People write in English, Tagalog,
Bisaya (Cebuano), or a mix, with slang, typos, abbreviations and emojis.

Return ONLY one JSON object, nothing else:
{"kind": "campus" | "smalltalk" | "offtopic", "english": "<what the person wants, as one clear English message>"}

kind:
- "campus": about the campus or this chatbot's job: locations, buildings, rooms, facilities,
  equipment, offices, courses and programs, instructors, enrollment, NEMSU news or information,
  lost or found items, concerns, reports, feedback, reservations, or asking for help with these.
- "smalltalk": greetings, thanks, compliments, jokes, feelings, "can I ask something?",
  asking about the chatbot, friendly chat, emojis only.
- "offtopic": anything else (homework answers, coding, general knowledge, politics, ...).

Use the earlier messages (if any) to understand words like "it", "there", "that one", "and the library?".
Fix typos and slang in "english". Keep names, room codes and acronyms. Do not answer the question.

Examples:
"asa ang cr dapit sa cite" -> {"kind":"campus","english":"Where is the comfort room near CITE?"}
"naa bay wifi sa library" -> {"kind":"campus","english":"Is there wifi in the library?"}
"gusto ko mag reklamo sa aircon" -> {"kind":"campus","english":"I want to file a concern about the aircon."}
"musta bro" -> {"kind":"smalltalk","english":"Hello, how are you?"}
"can i ask something" -> {"kind":"smalltalk","english":"Can I ask you something?"}
"who won the NBA finals" -> {"kind":"offtopic","english":"Who won the NBA finals?"}
"""

SMALLTALK_PROMPT = """You are NEMSAI, the friendly assistant of NEMSU Tandag Main Campus.
The person is making small talk. Reply warmly in 1 or 2 short sentences, in the SAME language the
person used (English, Tagalog or Bisaya), like a kind and relaxed friend. Then gently offer help
with campus things (locations, rooms, facilities, concerns, lost items, feedback, instructors).
Do not answer unrelated questions. Do not use emojis. Never claim to be human."""

_JSON = re.compile(r"\{.*\}", re.DOTALL)


def parse(text):
    """The model's JSON, or None when it did not give one."""
    match = _JSON.search((text or "").replace("```json", "").replace("```", ""))
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    kind = str(data.get("kind", "")).strip().lower()
    english = str(data.get("english", "")).strip()
    if kind not in ("campus", "smalltalk", "offtopic") or not english:
        return None
    return {"kind": kind, "english": english[:500]}


def rewrite(question, earlier, ask):
    """Ask the model what the person means. `ask` is ask_model (so tests can replace it)."""
    context = ""
    if earlier:
        context = "Earlier messages (newest first):\n" + "\n".join(f"- {e[:200]}" for e in earlier[:3]) + "\n\n"
    try:
        return parse(ask(REWRITE_PROMPT, f"{context}Message: {question}"))
    except Exception:
        return None


def smalltalk(question, ask):
    try:
        return (ask(SMALLTALK_PROMPT, question) or "").strip() or None
    except Exception:
        return None
