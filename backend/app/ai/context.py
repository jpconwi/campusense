"""
ai/context.py - builds the prompt for the language model.

Only the user's ROLE is shared with the AI. Name, email and Google ID
are never put in the prompt.
"""

from app.prompts.areaPrompt import AREA_PROMPT
from app.prompts.concernPrompt import CONCERN_PROMPT
from app.prompts.feedbackPrompt import FEEDBACK_PROMPT
from app.prompts.instructorPrompt import INSTRUCTOR_PROMPT
from app.prompts.locationPrompt import LOCATION_PROMPT
from app.prompts.nemsuPrompt import NEMSU_PROMPT
from app.prompts.reportPrompt import REPORT_PROMPT
from app.prompts.reservationPrompt import RESERVATION_PROMPT
from app.prompts.roomPrompt import ROOM_PROMPT
from app.prompts.studentPrompt import STUDENT_PROMPT
from app.prompts.systemPrompt import SYSTEM_PROMPT
from app.services import announcement_service, campus_service, room_service

ADMIN_PROMPT = """
==================================================
CURRENT USER: ADMINISTRATOR
==================================================

You are helping a campus administrator. Report counts, pending items,
users and statistics are retrieved by the backend from the database.
You must NEVER make up or estimate any of those numbers or records.
"""

ROLE_PROMPTS = {
    "student": STUDENT_PROMPT,
    "instructor": INSTRUCTOR_PROMPT,
    "admin": ADMIN_PROMPT,
}


def build_user_context(user):
    """The only user data the AI is allowed to see."""
    return {"role": user.role if user else "student"}


def build_system_prompt(db, role, extra=None):
    parts = [SYSTEM_PROMPT, NEMSU_PROMPT, LOCATION_PROMPT, AREA_PROMPT, ROOM_PROMPT]

    rooms = room_service.list_rooms(db)
    if rooms:
        parts.append("ROOM LIST (from the campus database):\n" + "\n".join(
            f"- {r['room_id']}: {r['name']}, {r['building']}, {r['room_type']}, "
            f"capacity {r['capacity']}, equipment {r['equipment']}, status {r['status']}"
            for r in rooms))

    extra = campus_service.list_info(db)
    if extra:
        parts.append("ADDITIONAL CAMPUS INFORMATION (from the campus database):\n" +
                     "\n".join(f"- {r['topic']}: {r['answer']}" for r in extra))

    posted = announcement_service.list_active(db)
    if posted:
        parts.append("CURRENT ANNOUNCEMENTS (posted by campus administrators; share them when "
                     "relevant and never invent details they do not give):\n" +
                     announcement_service.for_prompt(posted))

    if extra:                                   # e.g. NEMSU news articles found for this question
        parts.append(extra)

    parts += [ROLE_PROMPTS.get(role, STUDENT_PROMPT), CONCERN_PROMPT, REPORT_PROMPT,
              FEEDBACK_PROMPT, RESERVATION_PROMPT]
    parts.append(f"SYSTEM CONTEXT:\nCurrent user role: {role}")
    return "\n".join(parts)