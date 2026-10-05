"""prompts/locationPrompt.py - where the campus is, and the map link."""

CAMPUS_MAP_URL = (
    "https://www.google.com/maps/place/North+Eastern+Mindanao+State+University/"
    "@9.0390496,126.2138046,17.29z/data=!4m6!3m5!1s0x330239d78f6d4465:0x4000434f560ac4ef"
    "!8m2!3d9.0394399!4d126.2160314!16s%2Fm%2F02qbybq?entry=ttu"
)

# Map that can be shown inside the chat window (no API key needed).
CAMPUS_EMBED_URL = "https://www.google.com/maps?q=9.0394399,126.2160314&z=17&output=embed"

CAMPUS_LATITUDE = 9.0394399
CAMPUS_LONGITUDE = 126.2160314

CAMPUS_LOCATION_TEXT = (
    "NEMSU Tandag Main Campus is in Tandag City, Surigao del Sur, Philippines. "
    "Here is the map:"
)

LOCATION_PROMPT = f"""
==================================================
CAMPUS LOCATION AND MAP
==================================================

When a user asks where the NEMSU Tandag Main Campus is, how to get there,
or asks for the map, the system (not you) shows an interactive Google Map
card with this location:

Google Maps link: {CAMPUS_MAP_URL}
Coordinates: {CAMPUS_LATITUDE}, {CAMPUS_LONGITUDE}

If you must mention the location yourself, say it is in Tandag City,
Surigao del Sur and give the Google Maps link above.

Never invent street names, landmarks, travel times, distances or
jeepney/tricycle routes. This map link is only for the whole campus.
It does not show individual rooms or buildings.
"""
