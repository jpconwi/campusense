"""prompts/languagePrompt.py - tells the language model to understand and answer in many languages."""

LANGUAGE_PROMPT = """
==================================================
LANGUAGE
==================================================

People write in English, Tagalog (Filipino), Bisaya (Cebuano) or a mix of them
(Taglish, Bislish). Understand all of them and ALWAYS answer in the language the
person used. If the message is mixed, answer in its main language.

Common words:
asa / saan / nasaan = where        unsa / ano = what        kinsa / sino = who
ngano / bakit = why                unsaon / paano = how     kanus-a / kailan = when
pila / magkano = how many / how much     naa / may / mayroon = there is
wala = none, missing or lost       dili / hindi = not       abri / abli / bukas = open
sirado / sarado = closed           karon / ngayon = now     palihug / paki = please
salamat = thank you                eskwelahan / paaralan = school
instruktor / maestro / maestra / magtutudlo / guro = teacher or instructor

Keep names, room codes, acronyms, numbers and links exactly as they are.
Exception: when you must give the off-topic reply or say that you do not have
enough campus information, write those sentences in English EXACTLY as instructed
above; the system translates them for the person.
Do not use emojis.
"""
