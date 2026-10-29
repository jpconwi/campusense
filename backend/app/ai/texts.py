"""
ai/texts.py - every fixed (rule-based) reply of NEMSAI, in English, Tagalog and Bisaya.

TEXTS[key] = (English, Tagalog, Bisaya)
  * the engine writes the English text; ai/language.py swaps in the Tagalog or Bisaya
    version when the person wrote in that language.
  * {value} / {code} are filled in by the engine.
To add a language, add one more item to each tuple and to LANGS.
"""

import re

from app.prompts.locationPrompt import CAMPUS_LOCATION_TEXT
from app.prompts.systemPrompt import OFF_TOPIC_RESPONSE

LANGS = ("en", "tl", "ceb")

TEXTS = {
    "off_topic": (
        OFF_TOPIC_RESPONSE,
        "Pasensya na, makakatulong lang ako sa mga bagay na tungkol sa campus: mga pasilidad, "
        "kagamitan, reserbasyon, at mga concern sa campus.",
        "Pasensya, makatabang ra ko sa mga butang nga may kalabotan sa campus: mga pasilidad, "
        "kagamitan, reserbasyon, ug mga concern sa campus."),
    "clarify_some": (
        "I'm not sure I understood that. Did you mean one of these?\n\n"
        "Tap one below, or rephrase your question with more details.",
        "Hindi ako sigurado kung naintindihan kita. Isa ba ito sa mga ito?\n\n"
        "Pindutin ang isa sa ibaba, o sabihin ulit ang tanong mo nang mas detalyado.",
        "Dili ko sigurado nga nasabtan tika. Kini ba ang imong gipasabot?\n\n"
        "Pislita ang usa sa ubos, o isulti pag-usab ang imong pangutana nga mas detalyado."),
    "clarify_none": (
        "Sorry, I couldn't understand that or find an answer for it. "
        "Could you rephrase or add more details? For example: "
        "\"Where is the library?\", \"What is the NEMSU mission?\" or "
        "\"How do I reserve a room?\"",
        "Pasensya na, hindi ko naintindihan iyon o wala akong makitang sagot. "
        "Pwede mo bang sabihin ulit nang mas detalyado? Halimbawa: "
        "\"Nasaan ang library?\", \"Ano ang misyon ng NEMSU?\" o \"Paano mag-reserve ng kwarto?\"",
        "Pasensya, wala ko makasabot o wala koy makitang tubag. "
        "Pwede ka ba mosulti pag-usab nga mas detalyado? Pananglitan: "
        "\"Asa ang library?\", \"Unsa ang mission sa NEMSU?\" o \"Unsaon pag-reserve ug kwarto?\""),
    "private": (
        "I can't share private account information such as email addresses, "
        "account IDs, passwords, or other personal details.",
        "Hindi ko maibabahagi ang pribadong impormasyon ng account tulad ng email address, "
        "account ID, password, o iba pang personal na detalye.",
        "Dili nako mahatag ang pribadong impormasyon sa account sama sa email address, "
        "account ID, password, o uban pang personal nga detalye."),
    "enter_question": (
        "Please enter a question.",
        "Pakisulat ang tanong mo.",
        "Palihug isulat ang imong pangutana."),
    "greeting_student": (
        "Hi there! Great to see you 😊 I'm NEMSAI, your NEMSU Tandag Main Campus assistant. "
        "What can I help you with today? I can help with campus locations, rooms, facilities, "
        "concerns, reports, feedback and instructor availability.",
        "Hi! Masaya akong makausap ka 😊 Ako si NEMSAI, ang assistant mo sa NEMSU Tandag Main "
        "Campus. Ano ang maitutulong ko sa iyo ngayon? Maaari akong tumulong sa mga lokasyon, "
        "silid, pasilidad, concern, report, feedback at availability ng mga instructor.",
        "Hi! Nalipay ko nga nakig-istorya ta 😊 Ako si NEMSAI, ang assistant nimo sa NEMSU Tandag "
        "Main Campus. Unsa akong ikatabang nimo karon? Makatabang ko sa mga lokasyon, kwarto, "
        "pasilidad, concern, report, feedback ug availability sa mga instructor."),
    "greeting_instructor": (
        "Hi there! Great to see you 😊 I'm NEMSAI, your NEMSU Tandag Main Campus assistant. "
        "What can I help you with today? I can help with campus locations, rooms, facilities, "
        "reservations, concerns, reports, feedback and faculty availability reports.",
        "Hi! Masaya akong makausap ka 😊 Ako si NEMSAI, ang assistant mo sa NEMSU Tandag Main "
        "Campus. Ano ang maitutulong ko sa iyo ngayon? Maaari akong tumulong sa mga lokasyon, "
        "silid, pasilidad, reserbasyon, concern, report, feedback at faculty availability report.",
        "Hi! Nalipay ko nga nakig-istorya ta 😊 Ako si NEMSAI, ang assistant nimo sa NEMSU Tandag "
        "Main Campus. Unsa akong ikatabang nimo karon? Makatabang ko sa mga lokasyon, kwarto, "
        "pasilidad, reserbasyon, concern, report, feedback ug faculty availability report."),
    "greeting_admin": (
        "Hi there! Great to see you 😊 I'm NEMSAI, your NEMSU Tandag Main Campus assistant. "
        "What can I help you with today? I can find campus information or show pending concerns "
        "and reports from the database.",
        "Hi! Masaya akong makausap ka 😊 Ako si NEMSAI, ang assistant mo sa NEMSU Tandag Main "
        "Campus. Ano ang maitutulong ko sa iyo ngayon? Maaari akong maghanap ng impormasyon "
        "tungkol sa campus o magpakita ng mga pending na concern at report mula sa database.",
        "Hi! Nalipay ko nga nakig-istorya ta 😊 Ako si NEMSAI, ang assistant nimo sa NEMSU Tandag "
        "Main Campus. Unsa akong ikatabang nimo karon? Makapangita ko og impormasyon sa campus "
        "o makapakita sa mga pending nga concern ug report gikan sa database."),
    "greeting_default": (
        "Hi there! Great to see you 😊 I'm NEMSAI, your NEMSU Tandag Main Campus assistant. "
        "What can I help you with today? I can help with campus locations, rooms, facilities "
        "and equipment.",
        "Hi! Masaya akong makausap ka 😊 Ako si NEMSAI, ang assistant mo sa NEMSU Tandag Main "
        "Campus. Ano ang maitutulong ko sa iyo ngayon? Maaari akong tumulong sa mga lokasyon, "
        "silid, pasilidad at kagamitan.",
        "Hi! Nalipay ko nga nakig-istorya ta 😊 Ako si NEMSAI, ang assistant nimo sa NEMSU Tandag "
        "Main Campus. Unsa akong ikatabang nimo karon? Makatabang ko sa mga lokasyon, kwarto, "
        "pasilidad ug kagamitan."),
    "about_me": (
        "I'm NEMSAI, the NEMSU Tandag Main Campus assistant. I'm an AI, so I'm not from "
        "anywhere, but I live right here on the campus website. Ask me about campus locations, "
        "rooms, facilities, equipment, concerns, reports, feedback or instructor availability.",
        "Ako si NEMSAI, ang assistant ng NEMSU Tandag Main Campus. Isa akong AI, kaya wala akong "
        "pinanggalingan, pero nandito lang ako sa website ng campus. Magtanong ka tungkol sa mga "
        "lokasyon sa campus, kwarto, pasilidad, kagamitan, concern, report, feedback o "
        "availability ng instructor.",
        "Ako si NEMSAI, ang assistant sa NEMSU Tandag Main Campus. AI ko, mao nga wala koy "
        "gigikanan, pero naa ra ko diri sa website sa campus. Pangutana ra mahitungod sa mga "
        "lokasyon sa campus, kwarto, pasilidad, kagamitan, concern, report, feedback o "
        "availability sa instructor."),
    "about_system": (
        "This is NEMSAI, the NEMSU Tandag Main Campus assistant. It helps students, instructors "
        "and admins find campus locations, rooms and facilities, check instructor availability, "
        "report concerns and lost items, send feedback and (for instructors) request room "
        "reservations.",
        "Ito ang NEMSAI, ang assistant ng NEMSU Tandag Main Campus. Tumutulong ito sa mga "
        "estudyante, instructor at admin na hanapin ang mga lokasyon, kwarto at pasilidad sa "
        "campus, tingnan ang availability ng instructor, mag-report ng concern at nawalang gamit, "
        "magpadala ng feedback at (para sa mga instructor) mag-request ng reserbasyon ng kwarto.",
        "Kini ang NEMSAI, ang assistant sa NEMSU Tandag Main Campus. Nagatabang kini sa mga "
        "estudyante, instructor ug admin nga makit-an ang mga lokasyon, kwarto ug pasilidad sa "
        "campus, mahibaw-an ang availability sa instructor, mo-report ug concern ug nawala nga "
        "gamit, mopadala ug feedback ug (alang sa mga instructor) mo-request ug reserbasyon sa "
        "kwarto."),
    "languages": (
        "Yes! I understand English, Tagalog and Bisaya, and I reply in the language you use. "
        "You can also write in another language and I'll do my best to help.",
        "Oo! Naiintindihan ko ang English, Tagalog at Bisaya, at sasagot ako sa wikang ginagamit "
        "mo. Pwede ka ring sumulat sa ibang wika at gagawin ko ang makakaya ko para makatulong.",
        "Oo! Makasabot ko ug English, Tagalog ug Bisaya, ug motubag ko sa pinulongan nga imong "
        "gigamit. Pwede ka pud mosulat sa lain nga pinulongan ug buhaton nako ang akong labing "
        "maayo aron makatabang."),
    "help_ask": (
        "Sure, I'm happy to help! What help do you need? You can ask about campus locations, "
        "rooms, facilities and equipment, report a concern or a lost item, send feedback, or "
        "check instructor availability.",
        "Sige, masaya akong tumulong! Anong tulong ang kailangan mo? Pwede kang magtanong tungkol "
        "sa mga lokasyon sa campus, kwarto, pasilidad at kagamitan, mag-report ng concern o "
        "nawalang gamit, magpadala ng feedback, o tingnan ang availability ng instructor.",
        "Sige, malipay ko nga motabang! Unsang tabang ang imong kinahanglan? Pwede kang mangutana "
        "mahitungod sa mga lokasyon sa campus, kwarto, pasilidad ug kagamitan, mo-report ug concern "
        "o nawala nga gamit, mopadala ug feedback, o mo-check sa availability sa instructor."),
    "emoji_only": (
        "Hi there! What can I help you with today?",
        "Hi! Ano ang maitutulong ko sa iyo ngayon?",
        "Hi! Unsay matabang nako nimo karon?"),
    "ack": (
        "Okay! Let me know if you need anything else about the campus.",
        "Sige! Sabihin mo lang kung may kailangan ka pa tungkol sa campus.",
        "Sige! Sulti lang kung naa kay kinahanglan pa mahitungod sa campus."),
    "friends": (
        "Of course, we can be friends! I'm NEMSAI, your campus assistant. Just tell me what you "
        "need help with.",
        "Oo naman, pwede tayong maging magkaibigan! Ako si NEMSAI, ang assistant mo sa campus. "
        "Sabihin mo lang kung ano ang maitutulong ko.",
        "Sige, pwede ta nga mag-amigo! Ako si NEMSAI, ang imong assistant sa campus. Sultihi lang "
        "ko kung unsay maitabang nako."),
    "how_are_you": (
        "I'm doing great, thank you for asking! How can I help you today?",
        "Mabuti naman ako, salamat sa pagtanong! Paano kita matutulungan ngayon?",
        "Maayo ra ko, salamat sa pagpangutana! Unsaon nako pagtabang nimo karon?"),
    "thanks": (
        "You're welcome! Let me know if you need anything else about the campus.",
        "Walang anuman! Sabihin mo lang kung may kailangan ka pa tungkol sa campus.",
        "Walay sapayan! Sulti lang kung naa kay kinahanglan pa mahitungod sa campus."),
    "hours": (
        "I don't have the official opening hours of NEMSU or its offices, so I can't say if it is "
        "open right now. Please check with the school directly or look at its official page at "
        "nemsu.edu.ph.",
        "Wala akong opisyal na impormasyon tungkol sa oras ng bukas at sara ng NEMSU o ng mga "
        "opisina nito, kaya hindi ko masabi kung bukas ito ngayon. Pakitanong nang direkta sa "
        "paaralan o tingnan ang opisyal na pahina sa nemsu.edu.ph.",
        "Wala koy opisyal nga impormasyon sa oras sa pag-abri ug pag-sira sa NEMSU o sa mga "
        "opisina niini, mao nga dili nako masulti kung abri ba kini karon. Palihug pangutana "
        "direkta sa eskwelahan o tan-awa ang opisyal nga page sa nemsu.edu.ph."),
    "form_concern_student": (
        "I can help you report this campus concern. Please complete the form below.",
        "Matutulungan kitang i-report ang concern na ito sa campus. Pakikumpleto ang form sa ibaba.",
        "Matabangan tika pag-report niini nga concern sa campus. Palihug kompletoha ang form sa ubos."),
    "form_concern_instructor": (
        "I can help you report this facility concern. Please complete the form below.",
        "Matutulungan kitang i-report ang concern na ito sa pasilidad. Pakikumpleto ang form sa ibaba.",
        "Matabangan tika pag-report niini nga concern sa pasilidad. Palihug kompletoha ang form sa ubos."),
    "form_report_student": (
        "I can help you submit a campus report. Please complete the form below.",
        "Matutulungan kitang magsumite ng report sa campus. Pakikumpleto ang form sa ibaba.",
        "Matabangan tika pagsumite ug report sa campus. Palihug kompletoha ang form sa ubos."),
    "form_report_instructor": (
        "I can help you submit an instructor report. Please complete the form below.",
        "Matutulungan kitang magsumite ng report bilang instructor. Pakikumpleto ang form sa ibaba.",
        "Matabangan tika pagsumite ug report isip instructor. Palihug kompletoha ang form sa ubos."),
    "form_feedback": (
        "I'd be glad to take your feedback. Please complete the form below.",
        "Masaya akong tatanggap ng feedback mo. Pakikumpleto ang form sa ibaba.",
        "Malipay ko modawat sa imong feedback. Palihug kompletoha ang form sa ubos."),
    "form_reservation": (
        "I can help you send a reservation request. It stays pending until an administrator "
        "approves it. Please complete the form below.",
        "Matutulungan kitang magpadala ng request para sa reserbasyon. Mananatili itong pending "
        "hanggang aprubahan ng administrator. Pakikumpleto ang form sa ibaba.",
        "Matabangan tika pagpadala ug request sa reserbasyon. Magpabilin kining pending hangtod "
        "aprobahan sa administrator. Palihug kompletoha ang form sa ubos."),
    "form_faculty": (
        "I can help you submit your faculty availability report. Please complete the form below.",
        "Matutulungan kitang magsumite ng faculty availability report mo. Pakikumpleto ang form "
        "sa ibaba.",
        "Matabangan tika pagsumite sa imong faculty availability report. Palihug kompletoha ang "
        "form sa ubos."),
    "admin_forms": (
        "Admins manage submissions from the Admin Dashboard. You can ask me to show pending "
        "reports or concerns.",
        "Pinamamahalaan ng mga admin ang mga isinumite sa Admin Dashboard. Pwede mo akong "
        "utusang ipakita ang mga pending na report o concern.",
        "Ang mga admin mao ang mo-manage sa mga gisumite sa Admin Dashboard. Pwede nimo akong "
        "sugoon nga ipakita ang mga pending nga report o concern."),
    "reservation_denied": (
        "Sorry, room and facility reservations are only for instructors and faculty. "
        "If you need a room for a class or activity, please ask your instructor to "
        "reserve it. I can still help you report a concern or send feedback.",
        "Pasensya na, ang reserbasyon ng kwarto at pasilidad ay para lamang sa mga instructor at "
        "faculty. Kung kailangan mo ng kwarto para sa klase o aktibidad, pakisabi sa instructor "
        "mo na magpareserba. Matutulungan pa rin kitang mag-report ng concern o magpadala ng "
        "feedback.",
        "Pasensya, ang reserbasyon sa kwarto ug pasilidad para lang sa mga instructor ug faculty. "
        "Kung kinahanglan nimo ug kwarto para sa klase o aktibidad, palihug ingna ang imong "
        "instructor nga mo-reserve niini. Makatabang gihapon ko nimo pag-report ug concern o "
        "pagpadala ug feedback."),
    "lost_lost": (
        "Sorry to hear that. Please fill in the report form below with what you "
        "lost, where and when you last had it, so it can be checked.",
        "Pasensya sa nangyari. Pakipunan ang report form sa ibaba kung ano ang nawala sa iyo, "
        "saan at kailan mo huling hawak ito, para ma-check namin.",
        "Pasensya sa nahitabo. Palihug pun-a ang report form sa ubos kung unsa ang nawala nimo, "
        "asa ug kanus-a nimo kini katapusang gihuptan, aron ma-check kini."),
    "lost_found": (
        "Thank you for picking that up. Please fill in the report form below so "
        "the owner can be traced, and keep the item safe until it is claimed.",
        "Salamat sa pagpulot nito. Pakipunan ang report form sa ibaba para matunton ang may-ari, "
        "at ingatan muna ang gamit hanggang makuha ito ng may-ari.",
        "Salamat sa pagkuha niini. Palihug pun-a ang report form sa ubos aron matukib ang tag-iya, "
        "ug amoha una ang butang hangtod kini makuha sa tag-iya."),
    "lost_admin": (
        "Lost and found items are submitted as reports. You can ask me to show "
        "pending reports, or open Reports in the Admin Dashboard.",
        "Isinusumite bilang report ang mga nawala at nahanap na gamit. Pwede mo akong utusang "
        "ipakita ang mga pending na report, o buksan ang Reports sa Admin Dashboard.",
        "Ang mga nawala ug nakit-an nga gamit gisumite isip report. Pwede nimo akong sugoon nga "
        "ipakita ang mga pending nga report, o ablihi ang Reports sa Admin Dashboard."),
    "campus_location": (
        CAMPUS_LOCATION_TEXT,
        "Ang NEMSU Tandag Main Campus ay nasa Tandag City, Surigao del Sur, Pilipinas. "
        "Narito ang mapa:",
        "Ang NEMSU Tandag Main Campus naa sa Tandag City, Surigao del Sur, Pilipinas. "
        "Ania ang mapa:"),
    "my_email": ("Your account email is {value}.", "Ang email ng account mo ay {value}.",
                 "Ang email sa imong account kay {value}."),
    "my_name": ("Your account name is {value}.", "Ang pangalan ng account mo ay {value}.",
                "Ang ngalan sa imong account kay {value}."),
    "my_role": ("Your account type is {value}.", "Ang uri ng account mo ay {value}.",
                "Ang klase sa imong account kay {value}."),
    "no_room": (
        "I don't have a record for Room {code} in the campus room data.",
        "Wala akong tala para sa Room {code} sa datos ng mga kwarto sa campus.",
        "Wala koy rekord alang sa Room {code} sa datos sa mga kwarto sa campus."),
    "faculty_admin": (
        "Faculty absence reports are submitted by instructors. You can review them in Faculty Reports.",
        "Ang mga faculty absence report ay isinusumite ng mga instructor. Makikita mo ang mga ito "
        "sa Faculty Reports.",
        "Ang mga faculty absence report gisumite sa mga instructor. Makita nimo kini sa Faculty "
        "Reports."),
    "faculty_student": (
        "Only instructors can submit faculty availability reports. You can ask me "
        "whether an instructor is available, for example: \"Is Sir JP available today?\"",
        "Mga instructor lang ang pwedeng magsumite ng faculty availability report. Pwede mo akong "
        "tanungin kung available ang isang instructor, halimbawa: \"Available ba si Sir JP ngayon?\"",
        "Mga instructor ra ang makasumite ug faculty availability report. Pwede nimo akong "
        "pangutan-on kung available ba ang usa ka instructor, pananglitan: \"Available ba si Sir "
        "JP karon?\""),
}

# keys whose replies must stay serious (no emoji) and the ones that may be friendly
SERIOUS = {"off_topic", "clarify_some", "clarify_none", "private", "reservation_denied",
           "lost_lost", "lost_found", "lost_admin", "admin_forms", "no_room", "enter_question",
           "hours", "my_email", "my_name", "my_role"}
FRIENDLY_EMOJI = {"emoji_only": "😊", "help_ask": "🙂", "friends": "😊", "how_are_you": "😊", "greeting_student": "👋", "greeting_instructor": "👋", "greeting_admin": "👋",
                  "greeting_default": "👋", "about_me": "😊", "about_system": "😊",
                  "languages": "😊", "thanks": "😊", "campus_location": "📍"}


def en(key, **values):
    text = TEXTS[key][0]
    return text.format(**values) if values else text


def say(key, lang="en", **values):
    row = TEXTS[key]
    text = row[LANGS.index(lang)] if lang in LANGS else row[0]
    return text.format(**values) if values else text


# ---- reverse lookup: find which key an English reply came from (for translating it)
def _pattern(template):
    parts = re.split(r"(\{\w+\})", template)
    rx = "".join("(?P<%s>.+?)" % p[1:-1] if p.startswith("{") else re.escape(p) for p in parts)
    return re.compile("^" + rx + "$", re.DOTALL)


_EXACT = {}
_PATTERNS = []
for _key, _row in TEXTS.items():
    if "{" in _row[0]:
        _PATTERNS.append((_key, _pattern(_row[0])))
    else:
        _EXACT[_row[0]] = _key
        for _text in _row[1:]:
            _EXACT[_text] = _key


def key_of(answer):
    """The key of a fixed reply (in any language), or None."""
    answer = (answer or "").strip()
    if answer in _EXACT:
        return _EXACT[answer]
    for key, rx in _PATTERNS:
        if rx.match(answer):
            return key
    return None


def translate(answer, lang):
    """English fixed reply -> Tagalog / Bisaya. None when it is not a fixed reply."""
    if lang not in LANGS or lang == "en":
        return None
    answer = (answer or "").strip()
    if answer in _EXACT and TEXTS[_EXACT[answer]][0] == answer:
        return TEXTS[_EXACT[answer]][LANGS.index(lang)]
    for key, rx in _PATTERNS:
        m = rx.match(answer)
        if m:
            return TEXTS[key][LANGS.index(lang)].format(**m.groupdict())
    return None
