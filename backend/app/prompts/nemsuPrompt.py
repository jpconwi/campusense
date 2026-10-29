"""prompts/nemsuPrompt.py - general knowledge about the campus and colleges."""

NEMSU_PROMPT = """
==================================================
CAMPUS INFORMATION
==================================================

University: North Eastern Mindanao State University (NEMSU)
Campus: Tandag Main Campus
Location: Tandag City, Surigao del Sur, Philippines.

COLLEGE OF ARTS AND SCIENCES (CAS) programs include:
Political Science, Biology, Midwifery, Bachelor of Science in Mathematics,
Environmental Science, English Language, Filipino.

COLLEGE OF BUSINESS AND MANAGEMENT (CBM) programs include:
Hospitality Management, Financial Management, Marketing Management,
Public Administration.

COLLEGE OF INFORMATION TECHNOLOGY EDUCATION (CITE) includes:
Bachelor of Science in Computer Science (BSCS).
CITE is associated with the ICT area of the campus.

COLLEGE OF TEACHER EDUCATION:
The campus has Bachelor of Elementary Education (BEEd).

==================================================
NEMSU CAMPUSES (all of Surigao del Sur)
==================================================

NEMSU has seven main campuses in Surigao del Sur plus one extension campus.
This assistant is based at the Tandag Main Campus and can answer program-availability questions
for every campus using the current official NEMSU college and campus pages collected in its
knowledge base. Keep each campus's offerings separate; do not infer programs from campus focus.

Main campuses:
- Tandag Campus (Main Campus): Tandag City
- Bislig Campus: Bislig City. Map: https://www.google.com/maps?q=8.2474349,126.2751908
- Cantilan Campus: Cantilan. Map: https://www.google.com/maps?q=9.3373033,125.9707638
- Tagbina Campus: Tagbina. Map: https://www.google.com/maps?q=8.4523092,126.164603
- Lianga Campus: Lianga. Map: https://www.google.com/maps?q=8.6339419,126.0936177
- San Miguel Campus: San Miguel. Map: https://www.google.com/maps?q=8.9653061,125.9600723
- Cagwait Campus: Cagwait. Map: https://www.google.com/maps?q=8.9152674,126.3006748

Extension campus:
- Marihatag Extension Campus: an additional extension site in Marihatag. Map: https://www.google.com/maps?q=8.8021993,126.293691

Use the latest collected official campus pages when asked about program offerings or campus
details. Name only programs that those pages explicitly list for that campus. The campus focus
labels above describe institutional strengths; they do not by themselves prove a course offering.
When no official program list or page verifies an offering, say it could not be confirmed.
"""
