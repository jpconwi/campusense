"""
NEMSAI - Streamlit Cloud version.

Re-uses the FastAPI project's own Python code (backend/app/...) and the same
PostgreSQL database, so the chatbot, forms, rules and data are identical.
Login is Google (OpenID Connect) through Streamlit's st.login().
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="NEMSAI | NEMSU", page_icon="🎓", layout="wide")

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# --- secrets -> environment variables, BEFORE backend/app/config.py is imported
try:
    for _key, _val in st.secrets.items():
        if isinstance(_val, (str, int, float, bool)):
            os.environ.setdefault(str(_key).upper(), str(_val))
except Exception:
    pass
os.environ.setdefault("ADMIN_LOGIN_SECRET", "streamlit-not-used")   # React-only admin URL

from app import config                                            # noqa: E402
from app.ai.ai_engine import ask_ai                               # noqa: E402
from app.database import SessionLocal, init_db                    # noqa: E402
from app.security import CurrentUser, is_admin_email, is_nemsu_email   # noqa: E402
from app.services import (campus_service, common, concern_service, faculty_service,  # noqa: E402
                          feedback_service, report_service, reservation_service,
                          room_service, user_service)
from app.services.common import ValidationError                   # noqa: E402

STAFF_KINDS = {"Concerns": "concerns", "Reports": "reports",
               "Feedback": "feedback", "Reservations": "reservations"}
USER_PAGES = {
    "student": ["Campus AI", "My Concerns", "My Reports", "Feedback", "Reservations", "Profile"],
    "instructor": ["Campus AI", "Faculty Availability", "My Concerns", "My Reports",
                   "Feedback", "Reservations", "Profile"],
    "admin": ["Dashboard", "Campus AI", "Concerns", "Reports", "Faculty Reports",
              "Feedback", "Reservations", "Users", "Campus Info", "Profile"],
}
FORM_PAGE = {"concern_form": "My Concerns", "report_form": "My Reports",
             "feedback_form": "Feedback", "reservation_form": "Reservations",
             "faculty_form": "Faculty Availability"}


@st.cache_resource(show_spinner="Starting NEMSAI…")
def _startup():
    config.ensure_folders()
    init_db()
    return True


# ------------------------------------------------------------------ login
def login_screen():
    st.title("🎓 NEMSAI")
    st.subheader("NEMSU Tandag Main Campus assistant")
    st.write("Sign in with your official NEMSU Google account "
             f"(@{config.ALLOWED_DOMAIN}).")
    st.button("Continue with Google", type="primary", on_click=st.login)
    st.stop()


def get_current_user():
    """Google identity -> database user. Returns CurrentUser (role may be None)."""
    try:
        logged_in = bool(st.user.is_logged_in)
    except Exception:
        st.error("Google login is not configured. Add the [auth] section to the app's "
                 "Secrets (see .streamlit/secrets.toml.example).")
        st.stop()
    if not logged_in:
        login_screen()

    email = (st.user.get("email") or "").strip().lower()
    if not is_nemsu_email(email) or not st.user.get("email_verified", True):
        st.error("Please use your official NEMSU Google account.")
        st.button("Sign out", on_click=st.logout)
        st.stop()

    with SessionLocal() as db:
        if st.session_state.get("uid_email") != email:      # first run of this session
            name = (st.user.get("name") or email.split("@")[0]).strip()[:120]
            sub = str(st.user.get("sub") or email)
            row = user_service.login_user(db, sub, name, email, is_admin_email(email))
            st.session_state["uid"], st.session_state["uid_email"] = row.id, email
        row = user_service.get_user(db, st.session_state["uid"])
        if row is None or not row.is_active:
            st.error("This account is deactivated. Please contact the administrator.")
            st.button("Sign out", on_click=st.logout)
            st.stop()
        role = row.role
        if is_admin_email(row.email):
            role = "admin"
        elif role == "admin":
            role = None
        return CurrentUser(id=row.id, name=row.name, email=row.email, role=role,
                           created_at=row.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                           last_login=row.last_login.strftime("%Y-%m-%d %H:%M:%S"))


def role_screen(user):
    st.title(f"Welcome, {user.name}")
    st.write("Choose your account type. You can't change it later without an administrator.")
    choice = st.radio("I am a…", ["student", "instructor"], horizontal=True)
    if st.button("Continue", type="primary"):
        with SessionLocal() as db:
            if user_service.set_role_first_time(db, user.id, choice):
                st.rerun()
            st.error("Could not save that choice.")
    st.stop()


# ------------------------------------------------------------------- chat
def _too_many(limit=20, window=60):
    stamps = [t for t in st.session_state.get("asked", []) if time.time() - t < window]
    st.session_state["asked"] = stamps
    if len(stamps) >= limit:
        return True
    stamps.append(time.time())
    return False


def _go(page, prefill=None):
    st.session_state["page"] = page
    st.session_state["prefill"] = prefill or {}


def render_reply(item, idx):
    st.markdown(item["answer"])
    if item.get("type") == "map" and item.get("map"):
        m = item["map"]
        st.link_button(f"Open {m['title']} in Google Maps", m["url"])
        if m.get("embed_url"):
            components.iframe(m["embed_url"], height=300)
    if item.get("type") in FORM_PAGE:
        st.button("Open the form", key=f"form_{idx}", type="primary",
                  on_click=_go, args=(FORM_PAGE[item["type"]], item.get("prefill")))
    for n, text in enumerate(item.get("suggestions") or []):
        st.button(text, key=f"sug_{idx}_{n}",
                  on_click=lambda t=text: st.session_state.update(pending=t))


def page_chat(user):
    st.header("Campus AI")
    history = st.session_state.setdefault("chat", [])
    if not history:
        history.append({"role": "assistant", "item": {
            "type": "message",
            "answer": "Hi! I'm NEMSAI. Ask me about NEMSU, rooms, locations, "
                      "instructor availability, or file a concern, report, feedback "
                      "or reservation."}})
    for i, msg in enumerate(history):
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg["text"])
            else:
                render_reply(msg["item"], i)

    question = st.chat_input("Ask about NEMSU…") or st.session_state.pop("pending", None)
    if question:
        history.append({"role": "user", "text": question})
        if _too_many():
            item = {"type": "message", "answer": "Please wait a moment before asking again."}
        else:
            try:
                with st.spinner("Thinking…"), SessionLocal() as db:
                    item = ask_ai(db, question, user)
            except Exception as error:
                print("AI ERROR:", repr(error))
                item = {"type": "message", "answer": "Something went wrong. Please try again."}
        history.append({"role": "assistant", "item": item})
        st.rerun()


# ------------------------------------------------------------------ forms
def _done(row, text, pdf_fn=None):
    st.success(f"{text} (#{row['id']}, status: {row['status']})")
    if pdf_fn:
        path = pdf_fn(row["id"])
        if Path(path).exists():
            st.download_button("Download PDF", Path(path).read_bytes(),
                               file_name=Path(path).name, mime="application/pdf")


def _my_table(kind, user, hide=("id", "submitter_role")):
    with SessionLocal() as db:
        rows = common.list_rows(db, kind, user_id=user.id)
    cols = [(h, k) for h, k, private in common.COLUMNS[kind] if not private]
    st.subheader("Your submissions")
    if not rows:
        st.info("Nothing here yet.")
        return
    st.dataframe(pd.DataFrame([{h: r.get(k) for h, k in cols} for r in rows]),
                 hide_index=True, width="stretch")


def page_concerns(user):
    st.header("My Concerns")
    pf = st.session_state.get("prefill") or {}
    types = concern_service.CONCERN_TYPES
    with st.form("concern"):
        location = st.text_input("Location / Area", pf.get("location", ""))
        room = st.text_input("Room (optional)", pf.get("room", ""))
        ctype = st.selectbox("Concern type", types,
                             index=types.index(pf["concern_type"]) if pf.get("concern_type") in types else 0)
        desc = st.text_area("Description", pf.get("description", ""), max_chars=2000)
        when = st.date_input("Date")
        go = st.form_submit_button("Submit concern", type="primary")
    if go:
        try:
            with SessionLocal() as db:
                row = concern_service.create_concern(db, user, {
                    "location": location, "room": room, "concern_type": ctype,
                    "description": desc, "concern_date": str(when)}, None)
            _done(row, "Your concern was submitted.", concern_service.pdf_path)
        except ValidationError as e:
            st.error(str(e))
    _my_table("concerns", user)


def page_reports(user):
    st.header("My Reports")
    pf = st.session_state.get("prefill") or {}
    types = report_service.REPORT_TYPES
    with st.form("report"):
        location = st.text_input("Location", pf.get("location", ""))
        area = st.text_input("Area (optional)", pf.get("area", ""))
        room = st.text_input("Room (optional)", pf.get("room", ""))
        rtype = st.selectbox("Report type", types,
                             index=types.index(pf["report_type"]) if pf.get("report_type") in types else 0)
        desc = st.text_area("Description", pf.get("description", ""), max_chars=2000)
        when = st.date_input("Date")
        go = st.form_submit_button("Submit report", type="primary")
    if go:
        try:
            with SessionLocal() as db:
                row = report_service.create_report(db, user, {
                    "location": location, "area": area, "room": room, "report_type": rtype,
                    "description": desc, "report_date": str(when)}, None)
            _done(row, "Your report was submitted.", report_service.pdf_path)
        except ValidationError as e:
            st.error(str(e))
    _my_table("reports", user)


def page_feedback(user):
    st.header("Feedback")
    pf = st.session_state.get("prefill") or {}
    types = feedback_service.FEEDBACK_TYPES
    with st.form("feedback"):
        area = st.text_input("Campus area / facility", pf.get("area", ""))
        ftype = st.selectbox("Type", types,
                             index=types.index(pf["feedback_type"]) if pf.get("feedback_type") in types else 0)
        message = st.text_area("Message", pf.get("message", ""), max_chars=2000)
        when = st.date_input("Date")
        go = st.form_submit_button("Send feedback", type="primary")
    if go:
        try:
            with SessionLocal() as db:
                row = feedback_service.create_feedback(db, user, {
                    "area": area, "feedback_type": ftype, "message": message,
                    "feedback_date": str(when)})
            _done(row, "Thank you! Your feedback was submitted.", feedback_service.pdf_path)
        except ValidationError as e:
            st.error(str(e))
    _my_table("feedback", user)


def page_reservations(user):
    st.header("Reservations")
    st.caption("A request stays Pending until an administrator approves it.")
    pf = st.session_state.get("prefill") or {}
    with SessionLocal() as db:
        facilities = room_service.facility_names(db)
    with st.form("reservation"):
        facility = st.text_input("Facility / Room", pf.get("facility", ""))
        if facilities:
            st.caption("Known facilities: " + ", ".join(facilities[:15]))
        purpose = st.text_input("Purpose", pf.get("purpose", ""), max_chars=300)
        date = st.date_input("Date")
        c1, c2 = st.columns(2)
        start = c1.time_input("Start time")
        end = c2.time_input("End time")
        info = st.text_area("Additional information (optional)", max_chars=1000)
        go = st.form_submit_button("Send request", type="primary")
    if go:
        try:
            with SessionLocal() as db:
                row = reservation_service.create_reservation(db, user, {
                    "facility": facility, "purpose": purpose, "reservation_date": str(date),
                    "start_time": start.strftime("%H:%M"), "end_time": end.strftime("%H:%M"),
                    "additional_info": info})
            _done(row, "Your reservation request was sent.")
        except ValidationError as e:
            st.error(str(e))
    _my_table("reservations", user)


def page_faculty(user):
    st.header("Faculty Availability")
    with st.form("faculty"):
        reason = st.text_input("Reason", max_chars=300)
        c1, c2 = st.columns(2)
        start = c1.date_input("Date of absence")
        back = c2.date_input("Expected return")
        go = st.form_submit_button("Submit report", type="primary")
    if go:
        try:
            with SessionLocal() as db:
                row = faculty_service.create_faculty_report(db, user, {
                    "reason": reason, "start_date": str(start), "expected_return": str(back)})
            st.success(f"Report {row['display_id']} submitted (status: {row['status']}).")
        except ValidationError as e:
            st.error(str(e))
    if st.button("I'm available again"):
        with SessionLocal() as db:
            changed = faculty_service.mark_available_for_email(db, user.email)
        st.success("Marked as available." if changed else "No active absence to clear.")
    with SessionLocal() as db:
        rows = faculty_service.records_for_email(db, user.email)
    if rows:
        st.subheader("Your reports")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def page_profile(user):
    st.header("Profile")
    st.write(f"**Name:** {user.name}")
    st.write(f"**Email:** {user.email}")
    st.write(f"**Account type:** {user.role}")
    st.write(f"**Last login:** {user.last_login}")


# ------------------------------------------------------------------ admin
def page_dashboard(user):
    st.header("Dashboard")
    with SessionLocal() as db:
        cols = st.columns(4)
        for col, (label, kind) in zip(cols, STAFF_KINDS.items()):
            col.metric(f"Pending {label.lower()}", common.count_rows(db, kind, status="Pending"))
        data = {label: {s: common.count_rows(db, kind, status=s)
                        for s in common.TABLE_STATUSES[kind]}
                for label, kind in STAFF_KINDS.items()}
        st.subheader("Records by status")
        st.bar_chart(pd.DataFrame(data).fillna(0))
        st.caption(f"Active students: {user_service.count_role(db, 'student')} · "
                   f"instructors: {user_service.count_role(db, 'instructor')}")


def page_staff_records(kind, label):
    def render(user):
        st.header(label)
        statuses = common.TABLE_STATUSES[kind]
        pick = st.selectbox("Filter by status", ["All"] + statuses)
        with SessionLocal() as db:
            rows = common.list_rows(db, kind, status=None if pick == "All" else pick)
        heads = [(h, k) for h, k, _ in common.COLUMNS[kind]]
        if not rows:
            st.info("No records.")
            return
        st.dataframe(pd.DataFrame([{h: r.get(k) for h, k in heads} for r in rows]),
                     hide_index=True, width="stretch")
        st.subheader("Change status")
        c1, c2, c3 = st.columns([1, 2, 1])
        rid = c1.selectbox("Record #", [r["id"] for r in rows], key=f"id_{kind}")
        new = c2.selectbox("New status", statuses, key=f"st_{kind}")
        if c3.button("Update", key=f"up_{kind}", type="primary"):
            try:
                with SessionLocal() as db:
                    if kind == "reservations":
                        reservation_service.change_status(db, rid, new)
                    else:
                        common.update_status(db, kind, rid, new)
                st.success(f"#{rid} is now {new}.")
                st.rerun()
            except ValidationError as e:
                st.error(str(e))
    return render


def page_faculty_admin(user):
    st.header("Faculty Reports")
    with SessionLocal() as db:
        rows = list(reversed(faculty_service.load_records(db)))
    if not rows:
        st.info("No faculty reports.")
        return
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    rid = st.selectbox("Mark record # as available", [r["id"] for r in rows])
    if st.button("Mark available"):
        with SessionLocal() as db:
            ok = faculty_service.mark_available_by_id(db, rid)
        st.success("Updated.") if ok else st.warning("Already available.")


def page_users(user):
    st.header("Users")
    with SessionLocal() as db:
        rows = user_service.list_users(db)
    for r in rows:
        r.pop("google_id", None)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    others = [r for r in rows if r["id"] != user.id]
    if not others:
        return
    who = st.selectbox("User", others, format_func=lambda r: f"{r['name']} ({r['email']})")
    c1, c2 = st.columns(2)
    role = c1.selectbox("Role", ["student", "instructor"])
    if c1.button("Change role"):
        with SessionLocal() as db:
            ok = user_service.admin_set_role(db, who["id"], role)
        st.success("Role updated.") if ok else st.error("Could not change that role.")
    active = c2.toggle("Active", value=bool(who.get("is_active", True)), key=f"act_{who['id']}")
    if c2.button("Save active state"):
        with SessionLocal() as db:
            user_service.set_active(db, who["id"], active)
        st.success("Saved.")


def page_campus_info(user):
    st.header("Campus Info")
    st.caption("Facts the chatbot answers from. Delete a row to let the CSV re-seed it on restart.")
    with SessionLocal() as db:
        rows = campus_service.list_info(db)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.expander("Add a topic"):
        with st.form("campus_add"):
            topic = st.text_input("Topic", max_chars=80)
            keywords = st.text_input("Keywords (separated by ;)", max_chars=500)
            answer = st.text_area("Answer", max_chars=2000)
            if st.form_submit_button("Add"):
                try:
                    with SessionLocal() as db:
                        campus_service.add_info(db, {"topic": topic, "keywords": keywords,
                                                     "answer": answer})
                    st.success("Added.")
                    st.rerun()
                except ValidationError as e:
                    st.error(str(e))
    if rows:
        pick = st.selectbox("Delete a topic", rows, format_func=lambda r: r["topic"])
        if st.button("Delete topic"):
            with SessionLocal() as db:
                campus_service.delete_info(db, pick["id"])
            st.rerun()


# ------------------------------------------------------------------- main
def main():
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import OperationalError
    try:
        _startup()
    except OperationalError as error:
        url = make_url(config.DATABASE_URL)
        st.error("Could not connect to the database.")
        st.code(f"host={url.host}  port={url.port}  database={url.database}  user={url.username}")
        st.code(str(getattr(error, "orig", error))[:600])
        st.caption("host=localhost means DATABASE_URL was not read from Secrets. "
                   "A host without '.render.com' is Render's internal URL - use the External one.")
        st.stop()
    user = get_current_user()
    if user.role is None:
        role_screen(user)

    pages = {
        "Campus AI": page_chat, "My Concerns": page_concerns, "My Reports": page_reports,
        "Feedback": page_feedback, "Reservations": page_reservations,
        "Faculty Availability": page_faculty, "Profile": page_profile,
        "Dashboard": page_dashboard, "Faculty Reports": page_faculty_admin,
        "Users": page_users, "Campus Info": page_campus_info,
    }
    if user.role == "admin":
        for label, kind in STAFF_KINDS.items():
            pages[label] = page_staff_records(kind, label)
    menu = USER_PAGES[user.role]
    st.session_state.setdefault("page", menu[0] if user.role != "admin" else "Dashboard")
    if st.session_state["page"] not in menu:
        st.session_state["page"] = menu[0]

    with st.sidebar:
        st.markdown("### 🎓 NEMSAI")
        st.caption(f"{user.name} · {user.role}")
        st.radio("Menu", menu, key="page", label_visibility="collapsed")
        st.button("Sign out", on_click=st.logout)

    pages[st.session_state["page"]](user)


main()