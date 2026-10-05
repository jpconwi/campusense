"""prompts/areaPrompt.py - gates, canteens, library and how areas relate."""

AREA_PROMPT = """
==================================================
CAMPUS AREAS
==================================================

There are three main gates.
1st Gate: near the CBM departments.
2nd Gate: not far from the CBM area. The 1st Canteen is near this gate.
3rd Gate: near the ICT/CITE area.

1st Canteen: near the 2nd Gate and the CBM area.
2nd Canteen: near the Library and CAS.

The Library is near CAS and the 2nd Canteen.

LOCATION RELATIONSHIPS
CBM: near 1st Gate, relatively near 2nd Gate, 1st Canteen is near CBM.
CAS: near the Library and the 2nd Canteen.
CITE / ICT: near the 3rd Gate.

Never invent exact distances, building numbers or directions that are
not listed here.
"""
