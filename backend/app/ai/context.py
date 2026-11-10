"""
ai/context.py - builds the prompt for the language model.

Only the user's ROLE is shared with the AI. Name, email and Google ID
are never put in the prompt.
"""

from app.prompts.areaPrompt import AREA_PROMPT
from app.prompts.concernPrompt import CONCERN_PROMPT
from app.prompts.feedbackPrompt import FEEDBACK_PROMPT
from app.prompts.languagePrompt import LANGUAGE_PROMPT
from app.prompts.instructorPrompt import INSTRUCTOR_PROMPT
from app.prompts.locationPrompt import LOCATION_PROMPT
from app.prompts.nemsuPrompt import NEMSU_PROMPT
from app.prompts.reportPrompt import REPORT_PROMPT
from app.prompts.reservationPrompt import RESERVATION_PROMPT
from app.prompts.roomPrompt import ROOM_PROMPT
from app.prompts.studentPrompt import STUDENT_PROMPT
from app.prompts.systemPrompt import SYSTEM_PROMPT
from app.services import announcement_service, campus_service

ADMIN_PROMPT = """
==================================================
CURRENT USER: ADMINISTRATOR
==================================================

You are helping a campus administrator. Report counts, pending items,
users and statistics are retrieved by the backend from the database.
You must NEVER make up or estimate any of those numbers or records.

Help with campus administration tasks available to this role: reviewing assigned reports and
concerns, handling account reviews, faculty availability records, feedback, and announcements.
Do not tell an admin they can manage user roles, system/provider settings, room records, or campus
datasets; those controls are reserved for the Super Admin. Explain the correct dashboard workflow
and never claim to have changed a record from chat.
"""

SUPER_ADMIN_PROMPT = """
==================================================
CURRENT USER: SUPER ADMINISTRATOR
==================================================

You are assisting the Super Admin, who manages the NEMSAI platform and the full campus system.
Help with questions about the Super Admin dashboard, user and account management, campus admins,
rooms and campus datasets, reports and concerns, announcements, and system/provider settings.
Give clear steps that match the available dashboard features. The Super Admin can manage users,
review accounts, configure system settings, manage room and campus information, and review records.

You may explain how to complete an action, but do not claim to have changed settings, users, rooms,
or records from chat. Direct the user to the corresponding dashboard section for changes. When asked
about counts, pending items, users, or records, use only values returned by the backend; never make
up or estimate them. Respect the Super Admin's full administrative role while keeping user passwords,
private credentials, and secrets confidential.
"""

ROLE_PROMPTS = {
    "student": STUDENT_PROMPT,
    "instructor": INSTRUCTOR_PROMPT,
    "admin": ADMIN_PROMPT,
    "super_admin": SUPER_ADMIN_PROMPT,
}


def build_user_context(user):
    """The only user data the AI is allowed to see."""
    return {"role": user.role if user else "student"}


def build_system_prompt(db, role, news=None, rooms=None):
    parts = [SYSTEM_PROMPT, NEMSU_PROMPT, LOCATION_PROMPT, AREA_PROMPT, ROOM_PROMPT]

    if rooms:
        parts.append("RETRIEVED ROOM RECORDS (from the campus database; answer room questions "
                     "only from these records):\n" + "\n".join(
            f"- {r['room_id']}: {r['name']}, {r['building']}, department "
            f"{r.get('department') or 'not listed'}, {r['room_type']}, "
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

    if news:                                    # NEMSU news articles found for this question
        parts.append(news)

    parts.append(LANGUAGE_PROMPT)
    parts += [ROLE_PROMPTS.get(role, STUDENT_PROMPT), CONCERN_PROMPT, REPORT_PROMPT,
              FEEDBACK_PROMPT, RESERVATION_PROMPT]
    parts.append(f"SYSTEM CONTEXT:\nCurrent user role: {role}")
    return "\n".join(parts)
