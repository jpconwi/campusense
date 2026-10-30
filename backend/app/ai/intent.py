"""
ai/intent.py - decides WHAT the user wants (rule based, no LLM).

Faculty availability, forms, records and privacy are handled by code.
Only normal campus questions are sent to the language model.
"""

import re

from app.ai import preprocessing
from app.services import campus_service, faculty_service, room_service
from app.services.campus_service import normalize

# ----------------------------------------------------------------- helpers


def has(q, *phrases):
    """True when any phrase appears as whole word(s) in the normalized text."""
    padded = f" {q} "
    return any(f" {p} " in padded for p in phrases)


def is_learning_request(q):
    """Recognize learning intent by phrasing, without maintaining a list of subjects."""
    q = normalize(q)
    patterns = (
        r"\b(?:teach me|teach us|learn about|explain|define|help me understand)\b.+",
        r"\bwhat (?:is|are)\b.+",
        r"\bwhat does\b.+\bmean\b",
        r"\b(?:meaning|definition) of\b.+",
        r"\b(?:difference between|how does|how do)\b.+",
    )
    return any(re.search(pattern, q) for pattern in patterns)


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
    # Mentioning a personal concern ("my girlfriend", "my family") is not a campus
    # maintenance request. Require a campus object, place, or explicit filing action.
    return bool(has(q, *OBJECT_WORDS, *FACILITY_WORDS, "file", "submit", "report")
                or extract_area(q) or extract_concern_type(q))


def vague_concern(q):
    """A bare concern is an invitation to ask what is wrong, not a form command."""
    return (has(q, "concern", "concerns", "problem", "issue")
            and has(q, "i have", "ive got", "i got", "may concern", "may problema",
                    "i have a concern", "i have concern")
            and not (has(q, *OBJECT_WORDS, *FACILITY_WORDS, "file", "submit", "report",
                         "broken", "damaged", "complain", "complaint")
                     or extract_area(q) or extract_concern_type(q)))


_RECORD_DENIALS = (
    "not told you to show", "not tell you to show", "did not ask you to show",
    "didnt ask you to show", "never asked you to show", "not ask you to show",
    "without asking me", "not told you to list", "did not ask you to list",
    "didnt ask you to list", "never asked you to list", "not ask you to list",
    "you showed me my concerns", "you showed me my reports",
)


def denied_record_request(q):
    """Recognize a complaint that private records were shown without being requested."""
    return has(q, *_RECORD_DENIALS)


LOCATION_ASK = [
    "where", "wheres", "location", "locate", "address", "direction", "directions",
    "map", "how to get", "how do i get", "how to go", "how do i go", "way to",
    "find", "situated", "located", "route",
    "asa", "dapit", "diin", "nasaan", "saan", "asa dapit",       # Bisaya / Tagalog "where"
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
    asks_where = (has(q, *LOCATION_ASK, "maps", "google map", "google maps")
                  or has(q, "i mean", "i meant", "not the main", "not nemsu main", "not the department",
                         "not department", "wrong map", "main campus not"))
    if not asks_where and has(q, "available", "availability", "open", "closed", "hours",
                              "schedule", "time", "reserve"):
        return None                      # "is the library available?" is not a map question
    if asks_where or len(q.split()) <= 4 or place_service.is_only_a_place_name(q):
        if place_service.is_program_place_query(q) and not asks_where:
            return None                  # a bare course name asks about the program, not for a map
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
GREETING_PHRASES = ["hi", "hello", "hey", "hi there", "hello there", "good morning",
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


# "ouh", "ok", "sige", "i see": the person just acknowledges what was said
ACKS = {"ouh", "oh", "ohh", "ok", "okay", "oks", "okey", "okie", "k", "kk", "ah", "ahh", "aha", "ahh sige",
        "sige", "ge", "cge", "sge", "oo", "opo", "o", "hmm", "hm", "hmmm", "yes", "yeah", "yep", "yup",
        "ayos", "i see", "got it", "noted", "alright", "all right", "sure", "cool", "nice", "good",
        "ok lang", "okay lang", "ok na", "okay na", "ok sige", "okay sige", "sige na", "ah ok", "ah okay",
        "ah ok sige", "oh ok", "oh okay", "ouh ok", "ouh okay", "sige salamat", "ge sige", "nah", "nope",
        "wala", "dili", "no", "hindi"}

# "help me", "tabangi ko", "i need help", "pwede ka mutabang?" -> ask what help they need
HELP_WORDS = ["help", "tabang", "tabangi", "tabangan", "tulong", "tulungan", "patulong",
              "saklolo", "mutabang", "matabang", "makatabang"]
HELP_FILLER = {"me", "us", "please", "pls", "plss", "po", "opo", "can", "could", "would", "you", "i",
               "need", "want", "some", "a", "with", "to", "ko", "nako", "mo", "ka", "ako", "ba",
               "pwede", "pede", "palihug", "paki", "sir", "maam", "nemsai", "bot", "ai", "kog",
               "ug", "sa", "na", "lang", "gyud", "naman", "akong", "kinahanglan", "need", "talaga",
               "mag", "tabangi", "tabang", "tabangan", "help", "tulong", "tulungan", "patulong",
               "saklolo", "mutabang", "matabang", "makatabang", "kailangan", "pa", "oy", "uy", "hoy",
               "ha", "plz", "somebody", "someone", "anyone"}
FRIENDS = ["makig amigo", "makiamigo", "makipag amigo", "makipagkaibigan", "makipagkaibigan ako",
           "be my friend", "can we be friends", "friends tayo", "mag amigo", "maging magkaibigan",
           "amigo ta", "amigo tayo", "friends ta"]
HOW_ARE_YOU = ["how are you", "how are you doing", "hows it going", "how r u", "kumusta ka na",
               "kamusta ka na", "musta ka na", "unsa na", "kumusta na ka"]

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
    # Clean high-confidence typos against the official campus vocabulary before
    # classifying intent; keep `question` unchanged for form fields and replies.
    q = normalize(preprocessing.correct_question(db, question))
    original = question
    tokens = q.split()

    if not q:
        return {"intent": "empty"}

    if (has(q, "president", "suc president")
            and has(q, "nemsu", "university", "who", "name", "know", "current",
                    "did you know", "who is", "who was")):
        return {"intent": "nemsu_president"}

    if denied_record_request(q):
        return {"intent": "record_privacy_complaint"}
    if has(q, "0 10", "0 out of 10", "rating the system", "rate the system",
           "confusing system", "this system is confusing", "not related", "unrelated",
           "why did you send me a source", "why you send me a source", "why did you send me a map",
           "why did you send me library", "why did you send me an example"):
        return {"intent": "system_feedback"}
    if vague_concern(q):
        return {"intent": "concern_ask"}
    if (has(q, *CONCERN_WORDS, "problem", "issue", "upset")
            and has(q, "girlfriend", "boyfriend", "wife", "husband", "partner",
                    "relationship", "dating", "breakup")):
        return {"intent": "personal_relationship_concern"}

    if re.fullmatch(r"(?:(?:can|could|will|would) you )?teach me(?: something)?(?: please)?", q):
        return {"intent": "learn_ask"}

    if (has(q, "survive", "succeed", "do well", "handle", "manage")
            and has(q, "math", "course", "program", "college", "computer science", "bshm", "bscs")):
        return {"intent": "program_fit"}

    asks_offering = has(q, "available", "availability", "offered", "offer", "which campuses",
                        "what campus")
    asks_program_location = (has(q, "where", "located", "location")
                             and has(q, "course", "program", "degree", "major"))
    # Students commonly ask availability as a direct yes/no question, e.g.
    # "does NEMSU Tandag have BS Fisheries?" without saying "available".
    asks_degree_availability = (
        has(q, "has", "have", "offers", "offer", "offered", "available", "availability")
        and has(q, "bs", "bachelor", "bachelors", "degree", "program", "course", "bsc", "ba")
        and has(q, "tandag", "campus", "nemsu")
    )
    asks_bisaya_program_availability = (
        has(q, "naay", "naa")
        and has(q, "diri", "dinhi", "campus", "main", "tandag", "nemsu")
        and any(
            (row.get("topic", "").lower().startswith(("bachelor", "batsilyer", "master", "doctor"))
             and any(alias and f" {normalize(alias)} " in f" {q} "
                     for alias in (row.get("keywords") or "").split(";")))
            for row in campus_service.list_info(db)
        )
    )
    asks_program_list = (
        has(q, "courses", "programs", "degrees")
        and has(q, "nemsu", "university", "campus", "campuses", "tandag", "all campuses")
        and has(q, "all", "list", "what", "which", "offer", "offers", "offered", "available", "in")
    )
    if asks_program_list:
        return {"intent": "program_list"}
    if ((asks_offering and has(q, "course", "program", "campus", "campuses", "in", "at",
                               "where", "which")) or asks_program_location or asks_degree_availability
            or asks_bisaya_program_availability):
        return {"intent": "program_availability"}

    named_program = any(
        row.get("topic", "").lower().startswith(("bachelor", "batsilyer", "master", "doctor", "diploma"))
        and any(alias and f" {normalize(alias)} " in f" {q} "
                for alias in [row.get("topic", "")] + (row.get("keywords") or "").split(";"))
        for row in campus_service.list_info(db)
    )
    curriculum_question = (
        has(q, "curriculum", "prospectus")
        or (has(q, "semester", "sem") and has(q, "subject", "subjects", "course", "courses"))
        or (named_program and has(q, "subjects", "courses")
            and has(q, "what", "which", "list", "teach", "offer", "offered"))
        or (has(q, "subject", "subjects", "course", "courses")
            and bool(re.search(r"\b(?:bs|bsc|ba|bachelor of science|bachelor of arts)\s+", q))))
    if curriculum_question:
        return {"intent": "program_curriculum"}

    study_help = (has(q, "exam", "exams", "test", "tests", "quiz")
                  and has(q, "pass", "study", "prepare", "review", "help", "how to"))
    academic_subject = has(q, "subject", "subjects")
    if study_help or academic_subject:
        return {"intent": "general_tutor"}

    learn_request = re.search(
        r"\b(?:teach me about|teach me|learn about|learn|tell me about|explain)\s+(.+)", q)
    if learn_request and learn_request.group(1).strip():
        return {"intent": "learn_program", "topic": learn_request.group(1).strip()}

    # A student sharing what they study is small talk, not a request for the
    # location of a college merely because the course name matches campus data.
    course_share = (re.search(r"\bmy (?:course|program)(?: in [a-z0-9]+)? is .+", q)
                    or re.search(r"\bi (?:am |m )?(?:taking|studying|study) .+", q)
                    or re.search(r"\bi am a .+ student\b", q))
    if course_share and not has(q, "what", "where", "which", "how", "when"):
        return {"intent": "course_share"}

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

    # "ouh", "ok", "sige"
    if q in ACKS:
        return {"intent": "ack"}

    # "help me" / "tabangi ko" (nothing else said): ask what they need help with
    if has(q, *HELP_WORDS) and all(t in HELP_FILLER for t in tokens):
        return {"intent": "help_ask"}

    # "pede makig amigo?", "how are you?"
    if has(q, *FRIENDS):
        return {"intent": "friends"}
    if has(q, *HOW_ARE_YOU):
        return {"intent": "how_are_you"}

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
    elif (nouns and (status or list_words)
          and not has(q, "how do i") and not denied_record_request(q)):
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
        if has(q, "who", "which") and has(q, "instructor", "teacher", "professor", "faculty"):
            return {"intent": "faculty_availability_ask"}

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
