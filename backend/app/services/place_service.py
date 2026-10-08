"""
services/place_service.py - places INSIDE the NEMSU Tandag Main Campus that can be
shown as an embedded Google Map (gates, canteens, buildings, courts ...).

To add a place: add one line to PLACES.
    key: (display name, latitude, longitude, [words people may type])
Words are lowercase. Pure Python, no database.
"""

import re

PLACES = {
    "gate1": ("1st Gate", 9.039807, 126.216643, ["1st gate", "first gate", "gate 1"]),
    "gate2": ("2nd Gate", 9.039238, 126.217132, ["2nd gate", "second gate", "gate 2"]),
    "gate3": ("3rd Gate", 9.037956, 126.21562, ["3rd gate", "third gate", "gate 3"]),
    "canteen1": ("1st Canteen", 9.039086, 126.217126,
                 ["1st canteen", "first canteen", "canteen 1"]),
    "canteen2": ("2nd Canteen", 9.0391924, 126.2152126,
                 ["2nd canteen", "second canteen", "canteen 2"]),
    "ict": ("ICT Building (ICT Unit)", 9.0381124, 126.2151702,
            ["ict building", "ict unit", "ict area", "ict"]),
    "cite": ("CITE Building and Laboratories", 9.038193, 126.2154214,
             ["cite building", "cite laboratories", "cite laboratory", "cite lab",
              "cite labs", "cite"]),
    "midwifery": ("Midwifery Building", 9.0381378, 126.2157206,
                  ["midwifery building", "midwifery"]),
    "gym": ("Gym", 9.0385356, 126.2163785, ["gym", "gymnasium"]),
    "alumni_shed": ("Alumni Shed (Study Shed)", 9.038757, 126.215981,
                    ["alumni shed", "alumni study shed"]),
    "ssg_shed": ("SSG Study Shed", 9.0395402, 126.2153813,
                 ["ssg study shed", "ssg shed"]),
    "takraw": ("Takraw Court", 9.038802, 126.215895, ["takraw court", "takraw"]),
    "basketball1": ("Basketball and Pickleball Court", 9.038972, 126.215782,
                    ["basketball and pickleball court", "pickleball court", "pickleball"]),
    "basketball2": ("Second Basketball Court", 9.039295, 126.215514,
                    ["another basketball court", "second basketball court",
                     "2nd basketball court"]),
    "volleyball": ("Volleyball Court", 9.039446, 126.215346,
                   ["volleyball court", "volleyball"]),
    "clinic": ("Clinic", 9.039706, 126.215162, ["clinic", "school clinic", "campus clinic"]),
    "library": ("Library", 9.039372, 126.2150642, ["library"]),
    "cas": ("CAS Building", 9.0391116, 126.2148098,
            ["cas building", "college of arts and sciences building", "cas"]),
    "admin": ("NEMSU Administration Building", 9.0384389, 126.2148704,
              ["nemsu administration building", "administration building", "admin building"]),
    "research": ("Research Building", 9.039209, 126.214379,
                 ["research building"]),
    "law": ("Law Building", 9.039377, 126.214173, ["law building", "college of law"]),
    "cte": ("CTE Building", 9.039758, 126.214685,
            ["cte building", "college of teacher education building", "cte"]),
    "avc": ("Audio Visual Center (AVC)", 9.039996, 126.215299,
            ["audio visual center", "audio visual centre", "avc"]),
    "hostel": ("University Mini Hostel", 9.0401068, 126.21552,
               ["university mini hostel", "university mini hotel", "mini hostel",
                "mini hotel", "hostel"]),
    "president": ("Office of the University President", 9.0402325, 126.2156249,
                  ["office of the university president", "university president office",
                   "president office", "university president"]),
    "hrm": ("HRM Main Building", 9.040409, 126.21608,
            ["hrm main building", "hrm building", "hrm"]),
    "igp": ("IGP Office", 9.0403246, 126.2158972, ["igp office", "igp"]),
    "cbm": ("CBM Building", 9.0396482, 126.2166117,
            ["cbm building", "college of business and management building", "cbm"]),
    "cet": ("CET Building (unfinished)", 9.039042, 126.216574,
            ["cet unfinished building", "cet building", "cet"]),
    "electrical": ("Electrical and Automotive Building", 9.0387924, 126.2168236,
                   ["electrical and automotive building", "electrical and automotive",
                    "automotive building", "electrical building"]),
    "rotc": ("ROTC Office", 9.0385114, 126.2164844, ["rotc office", "rotc"]),
    "forest": ("NEMSU Forest", 9.03874, 126.214362, ["nemsu forest", "forest"]),
}

# a general word that could mean several places -> we ask which one
GROUPS = {
    "gate": (["gate1", "gate2", "gate3"], ["gate", "gates"]),
    "canteen": (["canteen1", "canteen2"], ["canteen", "canteens"]),
    "shed": (["alumni_shed", "ssg_shed"], ["study shed", "shed"]),
    "basketball": (["basketball1", "basketball2"], ["basketball court", "basketball"]),
    "court": (["takraw", "basketball1", "basketball2", "volleyball"], ["court", "courts"]),
}


def place_map(key):
    """(answer text, title, open-in-Google-Maps url, embed url) for one place."""
    name, lat, lng, _ = PLACES[key]
    url = f"https://www.google.com/maps?q={lat},{lng}"
    embed = f"https://www.google.com/maps?q={lat},{lng}&z=19&output=embed"
    text = f"{name} is inside the NEMSU Tandag Main Campus. Here is the map:"
    return text, name, url, embed


def _first_pos(padded, words):
    """Earliest position of any word as whole word(s), or None."""
    best = None
    for w in words:
        i = padded.find(f" {w} ")
        if i != -1 and (best is None or i < best[0] or (i == best[0] and len(w) > best[1])):
            best = (i, len(w))
    return best


def find_place(q):
    """q is the normalized question. Returns
       {"place": key}                    one specific place
       {"ask": [keys], "label": text}    a general word like "gate": ask which one
       None                              no place mentioned
    The place mentioned first in the question wins ("1st gate near cbm" -> 1st gate).
    """
    padded = f" {q} "
    best = None
    for key, (_, _, _, words) in PLACES.items():
        hit = _first_pos(padded, words)
        if hit and (best is None or hit[0] < best[0] or
                    (hit[0] == best[0] and hit[1] > best[1])):
            best = (hit[0], hit[1], key)
    if best:
        return {"place": best[2]}
    for label, (keys, words) in GROUPS.items():
        if _first_pos(padded, words):
            return {"ask": keys, "label": label}
    return None


def ask_which_text(found):
    names = [PLACES[k][0] for k in found["ask"]]
    options = ", ".join(names[:-1]) + " or " + names[-1]
    return (f"Which {found['label']} do you mean: {options}? "
            f"For example, ask: \"Where is the {names[0]}?\"")
