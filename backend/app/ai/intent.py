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


CONCERN_WORDS = ["concern", "concerns", "problem", "problems", "issue", "issues",
                 "complaint", "complaints"]
# "i have a concern in the cite cr", "problem with the aircon"
CONCERN_OWNERSHIP = ["i have", "ive got", "i got", "there is", "theres", "there are",
                     "may concern", "gusto ko", "want to", "wanna", "need to",
                     "would like to", "like to"]

LOST_WORDS = ["lost", "loss", "lose", "losing", "missing", "misplaced", "nawala",
              "nawalan", "nawad an", "nawagtang", "naiwan", "left behind", "stolen",
              "nakawan", "gikawat", "ninakaw"]
FOUND_WORDS = ["found", "nakita", "nakit an", "nakakita"]
ITEM_WORDS = [
    "phone", "cellphone", "cell phone", "mobile", "smartphone", "wallet", "bag",
    "backpack", "id", "ids", "umbrella", "key", "keys", "laptop", "tablet", "ipad",
    "charger", "earphones", "earphone", "earbuds", "airpods", "headphones",
    "calculator", "notebook", "book", "books", "flash drive", "flashdrive", "usb",
    "watch", "glasses", "eyeglasses", "jacket", "tumbler", "bottle", "money",
    "cp", "selpon", "pitaka", "payong", "susi", "gamit", "things", "belongings",
]


# "can you help me find my phone?", "gipangita nako akong wallet", "hanap ko ang bag ko"
FIND_PHRASES = ["find my", "finding my", "look for my", "looking for my", "search for my",
                "cant find", "cannot find", "can not find", "where is my", "wheres my",
                "where did i leave", "where did i put", "help me find", "hanap ko", "hinahanap ko",
                "hinahanap", "gipangita", "nangita", "pangitaa", "asa ang akong", "asa na akong",
                "nasaan ang", "nasaan na ang"]


def lost_found_request(q):
    """'i loss my phone', 'lost my wallet', 'i found an id' -> 'lost' / 'found' / None.

    A lost word alone ('i am lost', 'lost connection') is NOT enough: an item word
    must be there too, so directions questions keep working.
    """
    if not has(q, *ITEM_WORDS):
        return None
    if has(q, *LOST_WORDS):
        return "lost"
    if has(q, *FOUND_WORDS):
        return "found"
    # "find my phone" / "where is my wallet": it is the person's own thing, so it is lost
    if has(q, *FIND_PHRASES) and has(q, "my", "akong", "akoang", "akin", "ko", "nako"):
        return "lost"
    return None


def concern_request(q):
    """'i have concern in the cite cr', 'problem with the aircon', 'may concern ako'."""
    if not has(q, *CONCERN_WORDS):
        return False
    if has(q, "how do i", "how to", "how can i", "what is", "what are", "what does"):
        return False
    return bool(has(q, *CONCERN_OWNERSHIP, *OBJECT_WORDS, *FACILITY_WORDS)
                or extract_area(q) or extract_concern_type(q))


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


def _looks_like_form(q):
    """Same checks detect() uses for the reservation / concern / feedback / report forms."""
    if has(q, "reserve", "reserving", "reservation", "book a", "book the", "booking"):
        return True
    if lost_found_request(q) or concern_request(q):
        return True
    wants_report = has(q, "report", "file", "submit", "complain", "complaint")
    if has(q, *PROBLEM_WORDS) or (wants_report and has(q, "concern", "problem", "issue",
                                                       "complaint", *OBJECT_WORDS)):
        return True
    return has(q, "feedback", "suggestion", "suggest", "compliment", "comment",
               "report", "incident")


def announcements_request(q):
    """'any announcements?', 'what's new', 'upcoming events', 'who are the champions'."""
    if _looks_like_form(q):
        return None
    if not has(q, "announcement", "announcements", "news", "whats new", "events",
               "upcoming events", "champion", "champions", "winner", "winners", "updates"):
        return None
    if has(q, "champion", "champions", "winner", "winners"):
        category = "Champions"
    elif has(q, "events", "upcoming events"):
        category = "Event"
    elif has(q, "news"):
        category = "News"
    elif has(q, "updates"):
        category = "Update"
    else:
        category = None
    return {"category": category}


def rooms_request(q, original):
    """'what are available rooms', 'available rooms in cbm', 'list of rooms'."""
    if _looks_like_form(q) or room_service.extract_room_code(original):
        return None
    if not has(q, "room", "rooms", "classroom", "classrooms"):
        return None
    if not has(q, "available", "availability", "vacant", "free", "list", "show", "what",
               "which", "all", "any", "open", "unoccupied", "rooms"):
        return None
    return {"words": q.split(),
            "available": has(q, "available", "availability", "vacant", "free",
                             "open", "unoccupied")}


def other_campus_key(q):
    """'where is bislig campus', 'map of cantilan' -> 'bislig' / 'cantilan'.

    Returns None when no single campus is named, or when the question is about
    something else at that campus (dean, programs...), so only location-style
    questions or a bare campus name get a map.
    """
    from app.prompts.locationPrompt import OTHER_CAMPUSES
    if _looks_like_form(q):
        return None
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
    if _looks_like_form(q) or rooms_request(q, q):
        return None
    asks_where = has(q, *LOCATION_ASK, "maps", "google map", "google maps")
    if not asks_where and has(q, "available", "availability", "open", "closed", "hours",
                              "schedule", "time", "reserve"):
        return None                      # "is the library available?" is not a map question
    if asks_where or len(q.split()) <= 4 or place_service.is_only_a_place_name(q):
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
    elif kind == "lost_found":
        if code:
            prefill["room"] = f"Room {code}"
        if area:
            prefill["location"] = area
        prefill["report_type"] = "Lost & Found"
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
ABOUT_ME = ["taga asa ka", "taga saan ka", "where are you from", "where do you live",
            "who made you", "who created you", "who built you", "who developed you",
            "what is your name", "whats your name", "your name", "unsa imong ngalan",
            "unsa ngalan nimo", "ano pangalan mo", "ano ang pangalan mo", "are you a robot",
            "are you ai", "are you a bot", "are you real", "kinsa ka", "unsa ka", "sino ka",
            "kinsay naghimo nimo", "sino gumawa sayo"]
GREETING_PHRASES = ["hi", "hello", "hey", "help", "hi there", "hello there", "good morning",
                    "good afternoon", "good evening", "what can you do", "who are you",
                    "good day", "kumusta", "kamusta", "musta", "kumusta ka", "maayong buntag",
                    "maayong hapon", "maayong gabii", "maayong adlaw", "magandang umaga",
                    "magandang hapon", "magandang gabi", "magandang araw", "uy", "hoy"]

LANGUAGE_WORDS = ["tagalog", "bisaya", "cebuano", "binisaya", "visaya", "english", "filipino",
                  "language", "languages", "lenggwahe", "wika", "pinulongan", "taglish"]
LANGUAGE_ASK = ["kasabot ka", "kasabut ka", "makasabot ka", "makasabut ka", "kabalo ka", "kabalo ka mo",
                "do you understand", "do you speak", "can you speak", "can you understand",
                "naiintindihan mo", "naiintindihan mo ba", "marunong ka", "nakakaintindi ka",
                "what languages", "which languages", "unsa nga language", "anong wika",
                "anong lenggwahe", "unsang pinulongan"]
SYSTEM_WORDS = ["this system", "ni nga system", "ning system", "kini nga system", "ito nga system",
                "system na ito", "this website", "this app", "this chatbot", "this bot", "nemsai"]
SYSTEM_ASK = ["para asa", "para saan", "what is", "whats", "what does", "unsa", "ano", "purpose",
              "gamit", "used for", "for what"]
THANKS = ["thanks", "thank you", "thank u", "salamat", "maraming salamat", "daghang salamat",
          "salamat kaayo", "ty", "thanks po", "salamat po"]
HOURS_WORDS = ["open", "opened", "opening", "close", "closed", "closing", "abri", "abli", "abre",
               "bukas", "sarado", "sirado", "hours", "business hours", "office hours", "what time"]
HOURS_PLACE = ["nemsu", "campus", "school", "library", "registrar", "office", "eskwelahan",
               "paaralan", "tandag", "canteen", "gym"]


def asks_hours(q):
    """'abri run ang nemsu?', 'is the library open?' (opening hours are not in the campus data)."""
    return bool(has(q, *HOURS_WORDS) and has(q, *HOURS_PLACE)
                and not has(q, "form", "report", "concern", "reservation", "reserve", "feedback",
                            "open to", "open for", "open source", "open house"))


GREETING_FILLER = {"po", "opo", "haha", "hahaha", "hehe", "lol", "pls", "please", "nemsai", "bot",
                   "ai", "ha", "ba", "na", "there", "everyone", "all"}

# a short follow-up such as "asa dapit na?" / "where is it?" (no place named in it)
_FOLLOWUP_FILLER = {"asa", "dapit", "na", "ba", "diin", "nasaan", "saan", "where", "is", "it", "that",
                    "there", "exactly", "located", "ang", "po", "pa", "kini", "kana", "kadto",
                    "location", "unsa", "ni", "ha", "gyud", "man", "daw", "ang", "naa", "dapita", "yan"}
_ASKS_WHERE = ["asa", "where", "nasaan", "saan", "diin", "location", "located", "locate",
               "find", "map", "directions"]


def is_location_followup(q):
    tokens = q.split()
    return bool(tokens) and len(tokens) <= 5 and has(q, "asa", "where", "nasaan", "saan", "diin",
                                                    "dapit", "location") \
        and all(t in _FOLLOWUP_FILLER for t in tokens)


def asks_location(q):
    return bool(q) and not is_location_followup(q) and bool(has(q, *_ASKS_WHERE))


def detect(db, question, role):
    """Return a dict: {"intent": ..., plus extra data}."""
    q = normalize(question)
    original = question
    tokens = q.split()

    if not q:
        return {"intent": "empty"}

    # greetings / help
    if q in GREETING_PHRASES or " ".join(t for t in tokens if t not in GREETING_FILLER) in GREETING_PHRASES:
        return {"intent": "greeting"}

    # "taga asa ka?", "what is your name?", "are you a robot?"
    if has(q, *ABOUT_ME):
        return {"intent": "about_me"}

    # "kasabot ka ug tagalog ug bisaya?", "do you speak Tagalog?"
    if has(q, *LANGUAGE_ASK) and has(q, *LANGUAGE_WORDS):
        return {"intent": "languages"}

    # "para asa ni nga system?", "what is this system?"
    if has(q, *SYSTEM_WORDS) and has(q, *SYSTEM_ASK):
        return {"intent": "about_system"}

    # "thanks", "salamat kaayo"
    if (q in THANKS or (has(q, *THANKS) and len(tokens) <= 5)) and "?" not in original:
        return {"intent": "thanks"}

    # the user's own basic details
    if has(q, "my") and has(q, "email", "role", "account type", "name") \
            and not has(q, "password"):
        return {"intent": "my_info", "what": "email" if has(q, "email") else
                ("role" if has(q, "role", "account type") else "name")}
    if q in ("who am i", "whoami", "what is my role"):
        return {"intent": "my_info", "what": "role"}

    # other people's private data (a lost cellphone is not that)
    if not lost_found_request(q) and has(q, "email", "e mail", "emails", "gmail", "password", "passwords",
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

    # announcements, news, events, champions the admin posted
    ann = announcements_request(q)
    if ann:
        return {"intent": "announcements", **ann}

    # "available rooms", "rooms in cbm" -> the real room list from the database
    rooms = rooms_request(q, original)
    if rooms:
        return {"intent": "rooms_list", **rooms}

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

    # lost / found belongings -> report form (type: Lost & Found)
    lost = lost_found_request(q)
    if lost:
        return {"intent": "lost_item", "kind": lost,
                "prefill": _prefill(q, original, "lost_found")}

    # forms
    if has(q, "reserve", "reserving", "reservation", "book a", "book the", "booking"):
        return {"intent": "reservation_form",
                "prefill": _prefill(q, original, "reservation")}

    problem = has(q, *PROBLEM_WORDS)
    wants_report = has(q, "report", "file", "submit", "complain", "complaint")
    if problem or concern_request(q) or (
            wants_report and has(q, "concern", "problem", "issue", "complaint",
                                 *OBJECT_WORDS)):
        return {"intent": "concern_form", "prefill": _prefill(q, original, "concern")}

    if has(q, "feedback", "suggestion", "suggest", "compliment", "comment"):
        return {"intent": "feedback_form", "prefill": _prefill(q, original, "feedback")}

    if has(q, "report", "incident"):
        return {"intent": "report_form", "prefill": _prefill(q, original, "report")}

    return {"intent": "general"}