"""
ai/intent.py - decides WHAT the user wants (rule based, no LLM).

Faculty availability, forms, records and privacy are handled by code.
Only normal campus questions are sent to the language model.
"""

import re

from app.services import faculty_service, room_service
from app.services.campus_service import normalize

# ----------------------------------------------------------------- helpers


def has(q, *phrases):
    """True when any phrase appears as whole word(s) in the normalized text."""
    padded = f" {q} "
    return any(f" {p} " in padded for p in phrases)


STATUS_WORDS = [
    ("under review", "Under Review"), ("in progress", "In Progress"),
    ("pending", "Pending"), ("resolved", "Resolved"), ("rejected", "Rejected"),
    ("unresolved", "Pending"), ("approved", "Approved"), ("reviewed", "Reviewed"),
]
NOUNS = [
    ("concerns", "concerns"), ("concern", "concerns"),
    ("reports", "reports"), ("report", "reports"),
    ("feedback", "feedback"),
    ("reservations", "reservations"), ("reservation", "reservations"),
]

PROBLEM_WORDS = [
    "broken", "damaged", "defective", "faulty", "malfunction", "malfunctioning",
    "leaking", "leak", "clogged", "cracked", "busted", "spoiled", "flickering",
    "not working", "doesnt work", "does not work", "wont turn on",
    "not turning on", "out of order", "no water", "no electricity", "no power",
    "burned out", "burnt",
]
OBJECT_WORDS = [
    "projector", "fan", "aircon", "air conditioner", "airconditioner",
    "computer", "pc", "printer", "light", "lights", "bulb", "faucet", "toilet",
    "sink", "chair", "chairs", "table", "door", "window", "socket", "outlet",
    "tv", "monitor", "keyboard", "mouse", "wifi", "internet", "comfort room",
    "cr", "restroom",
]
FACILITY_WORDS = [
    "room", "lab", "laboratory", "library", "canteen", "gate", "building",
    "facility", "equipment", "hall", "gym", "court", "computer", "auditorium",
]

HONORIFICS = {"sir", "maam", "madam", "prof", "professor", "mr", "mrs", "ms",
              "dr", "engr", "instructor", "teacher"}
NAME_STOPWORDS = HONORIFICS | {
    "is", "are", "am", "available", "availability", "today", "tomorrow", "now",
    "currently", "in", "at", "school", "campus", "on", "there", "here",
    "working", "work", "can", "i", "find", "please", "where", "wheres", "when",
    "will", "would", "be", "return", "returning", "back", "come", "coming",
    "expected", "does", "did", "he", "she", "the", "to", "for", "of", "yet",
    "already", "faculty", "still", "absent", "present", "his", "her", "a", "an",
    "and", "he", "she", "okay", "ok", "know",
}

ABSENCE_PATTERNS = [
    "i am sick", "im sick", "i am ill", "im ill", "i am absent", "im absent",
    "i will be absent", "ill be absent", "i cannot come", "i cant come",
    "i cannot attend", "i cant attend", "i cannot work", "i cant work",
    "i will not come", "i wont come", "i will not work", "i wont work",
    "not coming to school", "cannot go to school", "cant go to school",
    "i am not feeling well", "im not feeling well", "i have a fever",
    "i wont be able to come", "i will not be able to come",
    "faculty absence", "faculty absent", "instructor absence",
    "instructor absent", "teacher absence", "teacher absent",
    "i am on leave", "im on leave",
]

AREA_MAP = [
    ("computer laboratory", "Computer Laboratory"), ("laboratory", "Laboratory"),
    ("lab", "Laboratory"), ("library", "Library"), ("canteen", "Canteen"),
    ("gate", "Gate"), ("cbm", "CBM area"), ("cas", "CAS area"),
    ("cite", "CITE / ICT area"), ("ict", "CITE / ICT area"),
]
TYPE_MAP = [
    ("Equipment", ["projector", "fan", "aircon", "air conditioner", "computer", "pc",
                   "printer", "tv", "monitor", "keyboard", "mouse", "wifi", "internet"]),
    ("Plumbing", ["faucet", "toilet", "sink", "leak", "leaking", "clogged", "no water",
                  "comfort room", "cr", "restroom"]),
    ("Electrical", ["light", "lights", "bulb", "socket", "outlet", "no electricity",
                    "no power"]),
    ("Furniture", ["chair", "chairs", "table", "desk"]),
    ("Building / Structure", ["door", "window", "ceiling", "wall", "roof", "floor"]),
]


LOCATION_ASK = [
    "where", "wheres", "location", "locate", "address", "direction", "directions",
    "map", "how to get", "how do i get", "how to go", "how do i go", "way to",
    "find", "situated", "located", "route",
]
CAMPUS_ANCHORS = ["nemsu", "campus", "tandag", "school", "university"]
# other NEMSU campuses: these questions must NOT get the Tandag map
OTHER_CAMPUS_WORDS = ["bislig", "cantilan", "tagbina", "lianga", "san miguel",
                      "cagwait", "marihatag", "campuses", "extension campus"]
SUB_AREA_WORDS = [
    "library", "canteen", "canteens", "gate", "gates", "room", "rooms", "lab", "labs",
    "laboratory", "building", "cas", "cbm", "cite", "cte", "ict", "gym", "court",
    "hall", "office", "registrar", "cr", "restroom", "comfort room",
    "sir", "maam", "madam", "prof", "professor", "instructor", "teacher", "faculty",
]


def other_campus_key(q):
    """'where is bislig campus', 'map of cantilan' -> 'bislig' / 'cantilan'.

    Returns None when no single campus is named, or when the question is about
    something else at that campus (dean, programs...), so only location-style
    questions or a bare campus name get a map.
    """
    from app.prompts.locationPrompt import OTHER_CAMPUSES
    found = [k for k in OTHER_CAMPUSES if has(q, k)]
    if len(found) != 1:
        return None
    if has(q, *LOCATION_ASK, "maps", "google map", "google maps") or len(q.split()) <= 4:
        return found[0]
    return None


def place_request(q):
    """'where is the library', 'map of 1st gate', 'cbm building' -> place_service result.

    Needs a location-style word (where, map, directions...) or a very short
    message, so 'what time does the library open' does not get a map.
    """
    from app.services import place_service
    if (has(q, *LOCATION_ASK, "maps", "google map", "google maps") or len(q.split()) <= 4
            or place_service.is_only_a_place_name(q)):
        return place_service.find_place(q)
    return None


def is_campus_location(q):
    """'where is nemsu', 'map of tandag campus', 'how do i get to the campus'."""
    if has(q, *SUB_AREA_WORDS):
        return False
    if has(q, *OTHER_CAMPUS_WORDS):
        return False
    # follow-ups like "show me the map" / "can you show the map?" need no campus word,
    # because the chat is already about the campus
    if has(q, "map", "maps", "google map", "google maps"):
        return True
    if not has(q, *CAMPUS_ANCHORS):
        return False
    return has(q, *LOCATION_ASK)


# --------------------------------------------------------- extraction
def extract_area(q):
    for word, label in AREA_MAP:
        if has(q, word):
            return label
    return None


def extract_concern_type(q):
    for label, words in TYPE_MAP:
        if has(q, *words):
            return label
    return None


def extract_faculty_name(q):
    """'is sir jp available today' -> ('jp', True)"""
    tokens = q.split()
    honorific = any(t in HONORIFICS for t in tokens)
    name = " ".join(t for t in tokens if t not in NAME_STOPWORDS)
    return (name or None), honorific


def _faculty_target(db, q):
    """Return the faculty name the question is about, or None."""
    name, honorific = extract_faculty_name(q)
    if not name:
        return None
    if honorific:
        return name
    if has(q, *FACILITY_WORDS):
        return None
    if faculty_service.has_record(db, name):
        return name
    return None


def _prefill(q, original, kind):
    prefill = {}
    code = room_service.extract_room_code(original)
    area = extract_area(q)
    if kind in ("concern", "report"):
        if code:
            prefill["room"] = f"Room {code}"
        if area:
            prefill["location"] = area
        ctype = extract_concern_type(q)
        if ctype and kind == "concern":
            prefill["concern_type"] = ctype
        prefill["description"] = original.strip()[:500]
    elif kind == "feedback":
        if area:
            prefill["area"] = area
    elif kind == "reservation":
        if code:
            prefill["facility"] = f"Room {code}"
        elif area:
            prefill["facility"] = area
    return prefill


# ----------------------------------------------------------- main entry
def detect(db, question, role):
    """Return a dict: {"intent": ..., plus extra data}."""
    q = normalize(question)
    original = question
    tokens = q.split()

    if not q:
        return {"intent": "empty"}

    # greetings / help
    if q in ("hi", "hello", "hey", "help", "hi there", "hello there", "good morning",
             "good afternoon", "good evening", "what can you do", "who are you"):
        return {"intent": "greeting"}

    # the user's own basic details
    if has(q, "my") and has(q, "email", "role", "account type", "name") \
            and not has(q, "password"):
        return {"intent": "my_info", "what": "email" if has(q, "email") else
                ("role" if has(q, "role", "account type") else "name")}
    if q in ("who am i", "whoami", "what is my role"):
        return {"intent": "my_info", "what": "role"}

    # other people's private data
    if has(q, "email", "e mail", "emails", "gmail", "password", "passwords",
           "google id", "google account", "phone number", "contact number",
           "mobile number", "cellphone", "home address"):
        return {"intent": "private"}

    # lists of records (admin: everything, others: only their own)
    nouns = [kind for word, kind in NOUNS if has(q, word)]
    nouns = list(dict.fromkeys(nouns))
    status = next((label for word, label in STATUS_WORDS if has(q, word)), None)
    list_words = has(q, "show", "list", "view", "how many", "all", "count", "display", "see")
    if role == "admin":
        if (nouns and (status or list_words)) or (status and list_words):
            return {"intent": "records", "kinds": nouns or ["concerns", "reports"],
                    "status": status}
    elif nouns and (status or has(q, "my", "status")) and not has(q, "how do i"):
        return {"intent": "records", "kinds": nouns, "status": status, "own": True}

    # faculty (answered from the CSV, never by the LLM)
    first_person = bool(tokens) and tokens[0] in ("i", "im", "ill", "ive")
    availability_phrases = ["available", "availability", "in school", "at school",
                            "in campus", "on campus", "working today", "work today",
                            "here today", "absent today", "present today"]
    if not first_person and has(q, *availability_phrases):
        target = _faculty_target(db, q)
        if target:
            return {"intent": "faculty_availability", "name": target}

    if not first_person and (has(q, "when") and has(q, "return", "back", "come back",
                                                    "coming back")
                             or has(q, "expected return")):
        target = _faculty_target(db, q)
        if target:
            return {"intent": "faculty_return", "name": target}

    if has(q, *ABSENCE_PATTERNS):
        return {"intent": "faculty_absence"}

    # where is one of the OTHER campuses -> map card for that campus
    campus_key = other_campus_key(q)
    if campus_key:
        return {"intent": "other_campus_location", "campus": campus_key}

    # where is a place inside the campus (gate, canteen, building ...) -> map card
    place = place_request(q)
    if place and "place" in place:
        return {"intent": "place_location", "place": place["place"]}
    if place and "ask" in place:
        return {"intent": "place_ask", "ask": place["ask"], "label": place["label"]}

    # where is the campus / show the map
    if is_campus_location(q):
        return {"intent": "campus_location"}

    # forms
    if has(q, "reserve", "reserving", "reservation", "book a", "book the", "booking"):
        return {"intent": "reservation_form",
                "prefill": _prefill(q, original, "reservation")}

    problem = has(q, *PROBLEM_WORDS)
    wants_report = has(q, "report", "file", "submit", "complain", "complaint")
    if problem or (wants_report and has(q, "concern", "problem", "issue", "complaint",
                                        *OBJECT_WORDS)):
        return {"intent": "concern_form", "prefill": _prefill(q, original, "concern")}

    if has(q, "feedback", "suggestion", "suggest", "compliment", "comment"):
        return {"intent": "feedback_form", "prefill": _prefill(q, original, "feedback")}

    if has(q, "report", "incident"):
        return {"intent": "report_form", "prefill": _prefill(q, original, "report")}

    return {"intent": "general"}