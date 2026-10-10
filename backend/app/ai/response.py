"""ai/response.py - builds the JSON answers sent to the chat window."""

from app.prompts.systemPrompt import OFF_TOPIC_RESPONSE  # noqa: F401  (re-exported)

NO_INFO = "I don't have enough campus information to answer that."

def clarify(suggestions=None):
    """Ask the user to rephrase instead of a dead-end 'I don't know'."""
    if suggestions:
        text = ("I'm not sure I understood that. Did you mean one of these?\n\n"
                "Tap one below, or rephrase your question with more details.")
    else:
        text = ("Sorry, I couldn't understand that or find an answer for it. "
                "Could you rephrase or add more details? For example: "
                "\"Where is the library?\", \"What is the NEMSU mission?\" or "
                "\"How do I reserve a room?\"")
    result = {"type": "message", "answer": text}
    if suggestions:
        result["suggestions"] = list(suggestions)
    return result


PRIVATE_REFUSAL = (
    "I can't share private account information such as email addresses, "
    "account IDs, passwords, or other personal details."
)

KIND_TITLES = {
    "concerns": "concerns", "reports": "reports",
    "feedback": "feedback", "reservations": "reservations",
}


def message(answer):
    return {"type": "message", "answer": answer}


def map_card(answer, map_url, embed_url, title="NEMSU Tandag Main Campus"):
    """Shows a Google Map card under the answer in the chat window."""
    return {"type": "map", "answer": answer,
            "map": {"title": title, "url": map_url, "embed_url": embed_url}}


def form(kind, answer, prefill=None):
    """kind: concern_form, report_form, feedback_form, reservation_form, faculty_form"""
    result = {"type": kind, "answer": answer}
    if prefill:
        result["prefill"] = prefill
    return result


def _short(text, limit=80):
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _line(kind, r, show_person):
    if kind == "concerns":
        place = r["location"] + (f", {r['room']}" if r.get("room") else "")
        text = f"#{r['id']} {r['concern_type']} — {place}: {_short(r['description'])}"
        person = f"{r['reporter_name']} ({r['reporter_email']})"
    elif kind == "reports":
        place = r["location"] + (f", {r['room']}" if r.get("room") else "")
        text = f"#{r['id']} {r['report_type']} — {place}: {_short(r['description'])}"
        person = f"{r['reporter_name']} ({r['reporter_email']})"
    elif kind == "feedback":
        text = f"#{r['id']} {r['feedback_type']} — {r['area']}: {_short(r['message'])}"
        person = f"{r['name']} ({r['email']})"
    else:
        text = (f"#{r['id']} {r['facility']} — {r['reservation_date']} "
                f"{r['start_time']}-{r['end_time']}: {_short(r['purpose'])}")
        person = f"{r['requester_name']} ({r['requester_email']})"
    parts = [text]
    if show_person:
        parts.append(person)
    parts.append(r["created_at"][:10])
    parts.append(r["status"])
    return "- " + " — ".join(parts)


def format_records(kind, rows, total, status, show_person, own=False):
    label = KIND_TITLES[kind]
    status_text = f"{status.lower()} " if status else ""
    scope = "your " if own else ""
    if total == 0:
        return f"There are no {status_text}{label} recorded{' for you' if own else ''}."
    title = f"{scope}{status_text}{label} ({total})"
    header = "**" + title[0].upper() + title[1:] + "**"
    lines = [_line(kind, r, show_person) for r in rows]
    text = header + "\n" + "\n".join(lines)
    if total > len(rows):
        extra = total - len(rows)
        text += f"\n\n…and {extra} more." + (
            " Open the Admin Dashboard to see all of them." if show_person else "")
    return text