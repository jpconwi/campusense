"""
ai/ai_engine.py - the brain of NEMSAI.

Order of work for every question:
  1. rule-based intent (greeting, private data, records, faculty, forms)
  2. campus information and room data from the CSV files
  3. strict off-topic check
  4. only then the Hugging Face model
"""

import difflib

from app.ai import intent as intents
from app.ai import response
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


def _greeting(role):
    base = ("Hello! I'm NEMSAI, the NEMSU Tandag Main Campus assistant. "
            "I can help with campus locations, rooms, facilities and equipment")
    extra = {
        "student": ", reservations, concerns, reports, feedback and instructor "
                   "availability.",
        "instructor": ", reservations, concerns, reports, feedback and your "
                      "faculty availability reports.",
        "admin": ". Ask me to show pending concerns or reports and I will read "
                 "them from the database.",
    }
    return response.message(base + extra.get(role, "."))


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
    return response.message("\n\n".join(blocks))


def _form_reply(user, found):
    role = user.role
    kind = found["intent"]

    if role == "admin":
        return response.message(
            "Admins manage submissions from the Admin Dashboard. You can ask me to "
            "show pending reports or concerns.")

    texts = {
        "concern_form": {
            "student": "I can help you report this campus concern. Please complete the form below.",
            "instructor": "I can help you report this facility concern. Please complete the form below.",
        },
        "report_form": {
            "student": "I can help you submit a campus report. Please complete the form below.",
            "instructor": "I can help you submit an instructor report. Please complete the form below.",
        },
        "feedback_form": {
            "student": "I'd be glad to take your feedback. Please complete the form below.",
            "instructor": "I'd be glad to take your feedback. Please complete the form below.",
        },
        "reservation_form": {
            "student": "I can help you send a reservation request. It stays pending until an "
                       "administrator approves it. Please complete the form below.",
            "instructor": "I can help you send a reservation request. It stays pending until an "
                          "administrator approves it. Please complete the form below.",
        },
    }
    return response.form(kind, texts[kind][role], found.get("prefill"))


def ask_ai(db, question, user):
    """Main function. `user` is the authenticated CurrentUser from the server."""
    question = str(question or "").strip()[:500]
    if not question:
        return response.message("Please enter a question.")

    role = user.role if user else "student"
    found = intents.detect(db, question, role)
    name = found["intent"]

    if name == "greeting":
        return _greeting(role)

    if knowledge_service.wants_article_text(question):      # "give me the text of that news"
        newest = knowledge_service.latest(db, 1)
        if newest:
            return response.message(knowledge_service.article_reply(newest[0]))

    if name == "my_info":                       # the user's OWN details only
        if found["what"] == "email":
            return response.message(f"Your account email is {user.email}.")
        if found["what"] == "name":
            return response.message(f"Your account name is {user.name}.")
        return response.message(f"Your account type is {role}.")

    if name == "campus_location":               # fixed answer + map, never the LLM
        return response.map_card(CAMPUS_LOCATION_TEXT, CAMPUS_MAP_URL, CAMPUS_EMBED_URL)

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
        return response.message(text)

    if name == "rooms_list":                    # real rooms from the admin's room list
        return response.message(room_service.rooms_answer(
            room_service.list_rooms(db), found["words"], found["available"]))

    if name == "other_campus_location":         # map card for another NEMSU campus
        text, title, url, embed = other_campus_map(found["campus"])
        return response.map_card(text, url, embed, title=title)

    if name == "place_location":                # gate, canteen, building ... map card
        text, title, url, embed = place_service.place_map(found["place"])
        info = campus_service.lookup(db, question)    # keep the written description too
        if info and "http" not in info:
            text = info
        return response.map_card(text, url, embed, title=title)

    if name == "place_ask":                     # "gate" / "canteen" -> which one?
        info = campus_service.lookup(db, question)
        hint = place_service.ask_which_text(found)
        return response.message(f"{info}\n\n{hint}" if info and "http" not in info else hint)

    if name == "private":
        return response.message(response.PRIVATE_REFUSAL)

    if name == "records":
        return _records(db, user, found)

    if name == "faculty_availability":
        return response.message(faculty_service.availability_reply(db, found["name"]))

    if name == "faculty_return":
        return response.message(faculty_service.return_reply(db, found["name"]))

    if name == "faculty_absence":
        if role == "instructor":
            return response.form(
                "faculty_form",
                "I can help you submit your faculty availability report. "
                "Please complete the form below.")
        if role == "admin":
            return response.message("Faculty absence reports are submitted by instructors. "
                                    "You can review them in Faculty Reports.")
        return response.message(
            "Only instructors can submit faculty availability reports. You can ask me "
            "whether an instructor is available, for example: \"Is Sir JP available today?\"")

    if name in ("concern_form", "report_form", "feedback_form", "reservation_form"):
        return _form_reply(user, found)

    # ---- campus information from the CSV files
    info = campus_service.lookup(db, question)
    if info:
        return response.message(info)

    info = campus_service.lookup_fuzzy(db, question)        # wrong spelling / short wording
    if info:
        return response.message(info)

    posted = announcement_service.match(db, intents.normalize(question))
    if posted:                                  # e.g. "when does the local mast start?"
        return response.message(posted)

    code = room_service.extract_room_code(question)
    if code:
        room = room_service.find_room(db, code)
        if room:
            return response.message(room_service.room_reply(room))
        return response.message(
            f"I don't have a record for Room {code} in the campus room data.")

    # ---- NEMSU news collected from the Newsroom (knowledge_documents)
    docs = knowledge_service.search(db, question)
    if docs:
        context = build_user_context(user)
        prompt = build_system_prompt(db, context["role"], news=knowledge_service.for_prompt(docs))
        answer = ask_model(prompt, question) or knowledge_service.fallback_answer(docs)
        return response.message(answer + "\n\n" + knowledge_service.sources_text(docs))

    # ---- strict off-topic protection
    if not _is_campus_related(question):
        suggestions = campus_service.suggest_topics(db, question)
        if suggestions:                           # misspelt campus topic, not off-topic
            return response.clarify(suggestions)
        return response.message(OFF_TOPIC_RESPONSE)

    # ---- the language model (role only, no private details)
    context = build_user_context(user)
    answer = ask_model(build_system_prompt(db, context["role"]), question)
    if not answer or response.NO_INFO.lower() in answer.lower():
        # nothing found (or the model gave up): ask the user to clarify
        return response.clarify(campus_service.suggest_topics(db, question))
    return response.message(answer)