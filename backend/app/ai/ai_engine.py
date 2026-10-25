"""
ai/ai_engine.py - the brain of NEMSAI.

Order of work for every question:
  1. rule-based intent (greeting, private data, records, faculty, forms)
  2. campus information and room data from the CSV files
  3. strict off-topic check
  4. only then the language model: Hugging Face first, then Cloudflare, Groq,
     Google and OpenRouter as automatic fallbacks (see model/systemAi.py)
"""

import difflib

from app.ai import intent as intents
from app.ai import language, response, style, texts
from app.ai.context import build_system_prompt, build_user_context
from app.model.systemAi import ask_model
from app.prompts.locationPrompt import (CAMPUS_EMBED_URL, CAMPUS_LOCATION_TEXT,
                                        CAMPUS_MAP_URL, other_campus_map)
from app.prompts.systemPrompt import OFF_TOPIC_RESPONSE
from app.services import (announcement_service, campus_service, common, faculty_service,
                          knowledge_service, place_service, room_service)
from app.services.campus_service import normalize

CAMPUS_KEYWORDS = [
    "nemsu", "campus", "tandag", "surigao", "university", "school", "college",
    "department", "cas", "cbm", "cite", "cte", "ict", "bscs", "beed", "course",
    "courses", "program", "programs", "library", "canteen", "canteens", "gate",
    "gates", "room", "rooms", "classroom", "classrooms", "laboratory",
    "laboratories", "lab", "labs", "building", "buildings", "facility",
    "facilities", "equipment", "projector", "fan", "aircon", "air conditioner",
    "computer", "printer", "chair", "desk", "table", "toilet", "restroom",
    "comfort room", "cr", "water", "faucet", "light", "electric", "reserve",
    "reservation", "borrow", "concern", "report", "feedback", "instructor",
    "teacher", "professor", "faculty", "sir", "maam", "student", "dean",
    "enrollment", "registrar", "gym", "court", "hall", "office", "maintenance",
    "map", "maps", "locate", "location", "directions", "john patrick", "conwi", "handsome", "genius", "ict area", "wifi",
]


_CAMPUS_WORDS = sorted({w for k in CAMPUS_KEYWORDS for w in normalize(k).split() if len(w) >= 5})


def _is_campus_related(question):
    q = normalize(question)
    if intents.has(q, *CAMPUS_KEYWORDS):
        return True
    # misspelt campus word, e.g. "libary", "canten", "reservaton"
    return any(len(w) >= 5 and difflib.get_close_matches(w, _CAMPUS_WORDS, n=1, cutoff=0.84)
               for w in q.split())


def _english(result):
    """Mark an answer written in English from the campus data: it is translated for Tagalog /
    Bisaya users (the map card and links stay as they are)."""
    result["english"] = True
    return result


def _data(text):
    return _english(response.message(text))


def _greeting(role):
    key = f"greeting_{role}" if f"greeting_{role}" in texts.TEXTS else "greeting_default"
    return response.message(texts.en(key))


def _records(db, user, found):
    """Real database records (never made up by the AI)."""
    own = not user.is_admin
    blocks = []
    for kind in found["kinds"]:
        status = found.get("status")
        if status and status not in common.TABLE_STATUSES[kind]:
            blocks.append(f"{kind.capitalize()} do not use the status '{status}'.")
            continue
        user_id = user.id if own else None
        rows = common.list_rows(db, kind, user_id=user_id, status=status, limit=10)
        total = common.count_rows(db, kind, status=status, user_id=user_id)
        blocks.append(response.format_records(kind, rows, total, status,
                                              show_person=not own, own=own))
    result = response.message("\n\n".join(blocks))
    result["serious"] = True                    # real data: never decorated
    return result


def _form_reply(user, found):
    role = user.role
    kind = found["intent"]

    if role == "admin":
        return response.message(texts.en("admin_forms"))

    if kind == "reservation_form" and role != "instructor":
        return response.message(texts.en("reservation_denied"))

    keys = {
        "concern_form": {"student": "form_concern_student", "instructor": "form_concern_instructor"},
        "report_form": {"student": "form_report_student", "instructor": "form_report_instructor"},
        "feedback_form": {"student": "form_feedback", "instructor": "form_feedback"},
        "reservation_form": {"instructor": "form_reservation"},
    }
    return response.form(kind, texts.en(keys[kind][role]), found.get("prefill"))


def _lost_item_reply(role, found):
    """Lost or found belongings: the campus report form, type 'Lost & Found'."""
    if role == "admin":
        return response.message(texts.en("lost_admin"))
    text = texts.en("lost_found" if found["kind"] == "found" else "lost_lost")
    return response.form("report_form", text, found.get("prefill"))


def ask_ai(db, question, user, earlier=None):
    """Main function. `user` is the authenticated CurrentUser from the server.

    `earlier` = this person's earlier questions in the same chat, newest first. It is only used
    for short follow-ups such as "asa dapit na?" ("where is it?").

    Languages: English, Tagalog and Bisaya are understood directly (fixed replies come back in
    the same language). Any other language is translated to English, answered, and translated
    back. A friendly emoji is added only sometimes (see ai/style.py).
    """
    question = str(question or "").strip()[:500]
    if not question:
        return response.message(texts.en("enter_question"))
    lang = language.detect(question)

    if lang == "other":                              # e.g. Spanish, Chinese, Korean
        english = language.to_english(question, ask_model)
        result = _answer(db, english or question, user, None, "en")
        if english:
            result = language.from_english(result, question, ask_model)
    else:
        result = _answer(db, question, user, earlier, lang)
        result = language.localize(result, lang)
        if result.pop("english", False) and lang in ("tl", "ceb"):
            result = language.from_english(result, question, ask_model)   # campus data -> their language
    result.pop("english", None)
    return style.add_emoji(result, question)


def _answer(db, question, user, earlier, lang):
    if earlier and intents.is_location_followup(normalize(question)):
        for old in earlier:
            if intents.asks_location(normalize(old)):
                return _answer(db, old, user, None, lang)   # the place they asked about before

    role = user.role if user else "student"
    found = intents.detect(db, question, role)
    name = found["intent"]

    if name == "greeting":
        return _greeting(role)
    if name in ("about_me", "about_system", "languages", "thanks"):
        return response.message(texts.en(name))

    if knowledge_service.wants_article_text(question):      # "give me the text of that news"
        newest = knowledge_service.latest(db, 1)
        if newest:
            return response.message(knowledge_service.article_reply(newest[0]))

    if name == "my_info":                       # the user's OWN details only
        if found["what"] == "email":
            return response.message(texts.en("my_email", value=user.email))
        if found["what"] == "name":
            return response.message(texts.en("my_name", value=user.name))
        return response.message(texts.en("my_role", value=role))

    if name == "campus_location":               # fixed answer + map, never the LLM
        return response.map_card(texts.en("campus_location"), CAMPUS_MAP_URL, CAMPUS_EMBED_URL)

    if name == "announcements":                 # what the admin posted: news, events, champions
        rows = announcement_service.list_active(db)
        if found["category"]:
            rows = [r for r in rows if r["category"] == found["category"]]
        newest = knowledge_service.latest(db, 3) if found["category"] in (None, "News", "Update") else []
        if rows or not newest:                    # what the admin posted (or the usual "none" message)
            text = announcement_service.chat_reply(db, found["category"])
            if newest:
                text += "\n\n" + knowledge_service.latest_text(newest)
        else:                                     # nothing posted by an admin: show the Newsroom only
            text = knowledge_service.latest_text(newest)
        return _data(text)

    if name == "rooms_list":                    # real rooms from the admin's room list
        return _data(room_service.rooms_answer(
            room_service.list_rooms(db), found["words"], found["available"]))

    if name == "other_campus_location":         # map card for another NEMSU campus
        text, title, url, embed = other_campus_map(found["campus"])
        return _english(response.map_card(text, url, embed, title=title))

    if name == "place_location":                # gate, canteen, building ... map card
        text, title, url, embed = place_service.place_map(found["place"])
        info = campus_service.lookup(db, question)    # keep the written description too
        if info and "http" not in info:
            text = info
        return _english(response.map_card(text, url, embed, title=title))

    if name == "place_ask":                     # "gate" / "canteen" -> which one?
        info = campus_service.lookup(db, question)
        hint = place_service.ask_which_text(found)
        return _data(f"{info}\n\n{hint}" if info and "http" not in info else hint)

    if name == "private":
        return response.message(texts.en("private"))

    if name == "records":
        return _records(db, user, found)

    if name == "faculty_availability":
        return _data(faculty_service.availability_reply(db, found["name"]))

    if name == "faculty_return":
        return _data(faculty_service.return_reply(db, found["name"]))

    if name == "faculty_absence":
        if role == "instructor":
            return response.form("faculty_form", texts.en("form_faculty"))
        if role == "admin":
            return response.message(texts.en("faculty_admin"))
        return response.message(texts.en("faculty_student"))

    if name == "lost_item":
        return _lost_item_reply(role, found)

    if name in ("concern_form", "report_form", "feedback_form", "reservation_form"):
        return _form_reply(user, found)

    # ---- campus information from the CSV files
    info = campus_service.lookup(db, question)
    if info:
        return _data(info)

    info = campus_service.lookup_fuzzy(db, question)        # wrong spelling / short wording
    if info:
        return _data(info)

    posted = announcement_service.match(db, intents.normalize(question))
    if posted:                                  # e.g. "when does the local mast start?"
        return _data(posted)

    code = room_service.extract_room_code(question)
    if code:
        room = room_service.find_room(db, code)
        if room:
            return _data(room_service.room_reply(room))
        return response.message(texts.en("no_room", code=code))

    # ---- "abri run ang nemsu?" / "is the library open?": opening hours are not in the campus data
    if intents.asks_hours(normalize(question)):
        hint = texts.say("hours", lang)            # joined with contact info, so translated here
        contact = campus_service.lookup(db, "nemsu contact numbers")
        return response.message(f"{hint}\n\n{contact}" if contact and "http" not in contact else hint)

    # ---- NEMSU news collected from the Newsroom (knowledge_documents)
    docs = knowledge_service.search(db, question)
    if docs and knowledge_service.wants_number(question):    # "how many ...?" needs a figure
        docs = knowledge_service.with_figures(docs)
    if docs:
        context = build_user_context(user)
        prompt = build_system_prompt(db, context["role"], news=knowledge_service.for_prompt(docs))
        answer = ask_model(prompt, question) or knowledge_service.fallback_answer(docs)
        return response.message(answer + "\n\n" + knowledge_service.sources_text(docs))

    # ---- vague follow-ups ("is that so?", "really?") -> ask what they mean
    if intents.has(normalize(question), "is that so", "is that true", "really", "thats it",
                   "that is it", "is that all", "what do you mean", "huh"):
        return response.clarify()

    # ---- strict off-topic protection
    if not _is_campus_related(question):
        suggestions = campus_service.suggest_topics(db, question)
        if suggestions:                           # misspelt campus topic, not off-topic
            return response.clarify(suggestions)
        return response.message(texts.en("off_topic"))

    # ---- the language model (role only, no private details)
    context = build_user_context(user)
    answer = ask_model(build_system_prompt(db, context["role"]), question)
    if not answer or response.NO_INFO.lower() in answer.lower():
        # nothing found (or the model gave up): ask the user to clarify
        return response.clarify(campus_service.suggest_topics(db, question))
    return response.message(answer)