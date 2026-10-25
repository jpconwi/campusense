"""Forms, privacy, faculty availability, admin management, charts and the AI chat."""

from datetime import datetime, timedelta

from app import config
from app.models import FacultyReport
from app.prompts.systemPrompt import OFF_TOPIC_RESPONSE
from app.services import room_service

TODAY = datetime.now().date().isoformat()
TOMORROW = (datetime.now().date() + timedelta(days=1)).isoformat()
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def concern_form(**over):
    data = {"location": "CITE building", "room": "Room 204", "concern_type": "Equipment",
            "description": "The projector is broken.", "concern_date": TODAY}
    data.update(over)
    return data


# ---------------------------------------------------------------- concerns
def test_concern_with_image(student, student2):
    r = student.post("/api/concerns", data=concern_form(),
                     files={"image": ("photo.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "Pending" and body["pdf_url"] == f"/api/pdf/concerns/{body['id']}"

    rows = student.get("/api/me/records/concerns").json()["rows"]
    assert len(rows) == 1 and rows[0]["reporter_name"] == "Sam Student"   # from the account
    assert rows[0]["image_filename"]
    # the owner sees the PDF + photo, another student does not
    assert student.get(body["pdf_url"]).status_code == 200
    assert student.get(body["pdf_url"]).headers["content-type"] == "application/pdf"
    img = f"/api/uploads/{rows[0]['image_filename']}"
    assert student.get(img).status_code == 200
    assert student2.get(body["pdf_url"]).status_code == 404
    assert student2.get(img).status_code == 404
    assert student2.get("/api/me/records/concerns").json()["rows"] == []


def test_concern_name_cannot_be_forged(student):
    student.post("/api/concerns", data=concern_form(reporter_name="Mallory", reporter_email="m@x.com"))
    row = student.get("/api/me/records/concerns").json()["rows"][0]
    assert row["reporter_name"] == "Sam Student" and row["reporter_email"] == "sam@nemsu.edu.ph"


def test_upload_validation(student):
    fake = student.post("/api/concerns", data=concern_form(),
                        files={"image": ("photo.png", b"this is not an image", "image/png")})
    assert fake.status_code == 400 and "valid image" in fake.json()["error"]
    ext = student.post("/api/concerns", data=concern_form(),
                       files={"image": ("virus.exe", PNG, "image/png")})
    assert ext.status_code == 400 and "PNG, JPG or WEBP" in ext.json()["error"]
    big = student.post("/api/concerns", data=concern_form(),
                       files={"image": ("big.png", PNG + b"0" * (6 * 1024 * 1024), "image/png")})
    assert big.status_code == 413
    assert student.get("/api/me/records/concerns").json()["rows"] == []


def test_required_fields_and_choices(student):
    r = student.post("/api/concerns", data=concern_form(location="", description=""))
    assert r.status_code == 400 and "required" in r.json()["error"]
    r = student.post("/api/concerns", data=concern_form(concern_type="Nonsense"))
    assert r.status_code == 400
    r = student.post("/api/concerns", data=concern_form(concern_date=TOMORROW))
    assert r.status_code == 400 and "future" in r.json()["error"]


def test_report_and_feedback(student, instructor):
    r = student.post("/api/reports", data={"location": "Library", "report_type": "Safety",
                                           "description": "Loose cable", "report_date": TODAY})
    assert r.status_code == 200 and r.json()["status"] == "Pending"
    f = instructor.post("/api/feedback", data={"area": "Library", "feedback_type": "Compliment",
                                               "message": "Great place", "feedback_date": TODAY})
    assert f.status_code == 200 and f.json()["pdf_url"].startswith("/api/pdf/feedback/")
    assert instructor.get(f.json()["pdf_url"]).status_code == 200


# ------------------------------------------------------------- reservations
def reservation(**over):
    data = {"facility": "Computer Laboratory", "purpose": "Class", "reservation_date": TOMORROW,
            "start_time": "09:00", "end_time": "11:00"}
    data.update(over)
    return data


def test_reservation_is_pending_and_validated(instructor):
    r = instructor.post("/api/reservations", data=reservation())
    assert r.status_code == 200 and r.json()["status"] == "Pending"
    bad = instructor.post("/api/reservations", data=reservation(start_time="11:00", end_time="09:00"))
    assert bad.status_code == 400 and "after the start" in bad.json()["error"]
    past = instructor.post("/api/reservations", data=reservation(reservation_date="2020-01-01"))
    assert past.status_code == 400


def test_students_cannot_reserve(student):
    r = student.post("/api/reservations", data=reservation())
    assert r.status_code == 403 and "instructors" in r.json()["error"].lower()
    assert student.get("/api/me/records/reservations").status_code == 403
    nav = [item["path"] for item in student.get("/api/auth/me").json()["nav"]]
    assert "/reservations" not in nav


def test_chat_tells_students_reservations_are_for_instructors(student):
    answer = student.post("/api/ask", json={"question": "I want to reserve a room"}).json()
    assert answer["type"] != "reservation_form"
    assert "instructor" in answer["answer"].lower()


def test_admin_approval_and_overlap(instructor, instructor2, admin):
    student, student2 = instructor, instructor2
    a = student.post("/api/reservations", data=reservation()).json()["id"]
    b = student2.post("/api/reservations", data=reservation(start_time="10:00", end_time="12:00")).json()["id"]
    assert admin.post(f"/api/admin/records/reservations/{a}/status", json={"status": "Approved"}).status_code == 200
    r = admin.post(f"/api/admin/records/reservations/{b}/status", json={"status": "Approved"})
    assert r.status_code == 400 and "overlaps" in r.json()["error"]
    # new overlapping requests are refused up front, back-to-back is fine
    r = student2.post("/api/reservations", data=reservation(start_time="10:30", end_time="11:30"))
    assert r.status_code == 400 and "already reserved" in r.json()["error"]
    assert student2.post("/api/reservations", data=reservation(start_time="11:00", end_time="12:00")).status_code == 200


# ------------------------------------------------------------ admin manage
def test_admin_dashboard_counts_and_lists(student, admin):
    student.post("/api/concerns", data=concern_form())
    student.post("/api/reports", data={"location": "Gate", "report_type": "Security",
                                       "description": "Door open", "report_date": TODAY})
    d = admin.get("/api/admin/dashboard").json()
    stats = dict((k, v) for k, v in d["stats"])
    assert stats["Pending Concerns"] == 1 and stats["Total Reports"] == 1
    assert stats["Total Students"] == 1
    assert d["charts"]["concern_status"]["total"] == 1                    # chart = real count
    assert d["charts"]["report_status"]["total"] == 1
    assert d["recent_concerns"][0]["reporter_name"] == "Sam Student"

    lst = admin.get("/api/admin/records/concerns").json()
    row = lst["rows"][0]
    assert row["reporter_email"] == "sam@nemsu.edu.ph" and "projector" in row["description"]
    assert row["submitter_role"] == "student"
    assert admin.get("/api/admin/records/concerns?status=Resolved").json()["rows"] == []
    assert admin.get("/api/admin/records/nonsense").status_code == 404


def test_status_workflow_is_visible_in_chat(student, admin):
    cid = student.post("/api/concerns", data=concern_form()).json()["id"]
    assert "Pending" in student.ask("What is the status of my concern?")["answer"]
    assert admin.post(f"/api/admin/records/concerns/{cid}/status", json={"status": "Under Review"}).status_code == 200
    assert "Under Review" in student.ask("What is the status of my concern?")["answer"]
    admin.post(f"/api/admin/records/concerns/{cid}/status", json={"status": "Resolved"})
    assert "Resolved" in student.ask("What is the status of my concern?")["answer"]
    assert admin.post(f"/api/admin/records/concerns/{cid}/status", json={"status": "Bogus"}).status_code == 400


def test_admin_chat_reads_real_records(student, student2, admin, prompts):
    student.post("/api/reports", data={"location": "Library", "report_type": "Safety",
                                       "description": "Loose cable", "report_date": TODAY})
    a = admin.ask("Show pending reports.")["answer"]
    assert "Loose cable" in a and "sam@nemsu.edu.ph" in a
    mine = student.ask("Show pending reports.")["answer"]
    assert "Loose cable" in mine and "sam@nemsu.edu.ph" not in mine         # own only
    assert "Loose cable" not in student2.ask("Show pending reports.")["answer"]
    assert prompts == []                                                     # never the LLM


def test_user_management(student, admin, client):
    users = admin.get("/api/admin/users").json()["rows"]
    assert {u["email"] for u in users} == {"sam@nemsu.edu.ph", "admin@nemsu.edu.ph"}
    assert all("google_id" not in u for u in users)
    sam = next(u for u in users if u["email"] == "sam@nemsu.edu.ph")
    assert admin.post(f"/api/admin/users/{sam['id']}/role", json={"role": "instructor"}).status_code == 200
    assert student.me()["user"]["role"] == "instructor"
    assert admin.post(f"/api/admin/users/{sam['id']}/role", json={"role": "admin"}).status_code == 400
    me = next(u for u in users if u["email"] == "admin@nemsu.edu.ph")
    assert admin.post(f"/api/admin/users/{me['id']}/active", json={"active": False}).status_code == 400
    # deactivate: the open session stops working and a new login is refused
    assert admin.post(f"/api/admin/users/{sam['id']}/active", json={"active": False}).status_code == 200
    assert student.post("/api/ask", json={"question": "hi"}).status_code == 401
    again = client()
    r = again.google_login("sam@nemsu.edu.ph")
    assert r.headers["location"] == "/login?error=deactivated"


def test_rooms_and_campus_admin(admin, student):
    assert admin.post("/api/admin/rooms", json={"room_id": "204", "name": "Room 204",
                                                "building": "CITE", "capacity": 40,
                                                "equipment": "Projector"}).status_code == 200
    assert admin.post("/api/admin/rooms", json={"room_id": "204", "name": "x"}).status_code == 400  # duplicate
    assert admin.post("/api/admin/rooms", json={"room_id": "", "name": "x"}).status_code == 400
    rooms = admin.get("/api/admin/rooms").json()["rows"]
    assert len(rooms) == 1
    # the AI answers room questions from the table, never invents them
    ans = student.ask("Tell me about Room 204")["answer"]
    assert "Room 204" in ans and "Projector" in ans and "Capacity: 40" in ans
    assert "don't have a record for Room 999" in student.ask("What about room 999?")["answer"]
    assert student.me()["facilities"] == ["Room 204"]
    assert admin.delete(f"/api/admin/rooms/{rooms[0]['id']}").status_code == 200

    assert admin.post("/api/admin/campus", json={"topic": "Registrar", "keywords": "registrar office",
                                                 "answer": "The Registrar is in the main building."}).status_code == 200
    assert "main building" in student.ask("Where is the registrar office?")["answer"]
    assert admin.post("/api/admin/campus", json={"topic": "registrar", "keywords": "a", "answer": "b"}).status_code == 400


# ----------------------------------------------------------------- faculty
def add_faculty(db, name, status="Absent", email="", ret="2026-12-31"):
    db.add(FacultyReport(instructor=name, reason="sick", start_date=datetime.now().date(),
                         expected_return=datetime.fromisoformat(ret).date(), status=status,
                         instructor_email=email))
    db.commit()


def test_availability_from_the_table_not_the_llm(student, db, prompts):
    add_faculty(db, "john patrick conwi")
    a = student.ask("Is Sir JP available today?")["answer"]
    assert "currently unavailable" in a and "2026-12-31" in a
    b = student.ask("When will Sir JP return?")["answer"]
    assert "expected to return on 2026-12-31" in b
    assert "don't have an availability record" in student.ask("Is Sir Nobody available today?")["answer"]
    assert prompts == []


def test_newest_record_wins_and_library_is_not_faculty(student, db):
    add_faculty(db, "jp")
    add_faculty(db, "jp", status="Available")
    assert "currently recorded as available" in student.ask("Is Sir JP available?")["answer"]
    assert "Library" in student.ask("Is the library available?")["answer"]


def test_instructor_submits_report(instructor, student, student2, admin, db):
    form = instructor.ask("I cannot work today.")
    assert form["type"] == "faculty_form"
    assert student.ask("I cannot work today.")["type"] == "message"          # students get no form
    r = instructor.post("/api/faculty/submit", data={"reason": "Fever", "start_date": TODAY,
                                                     "expected_return": TOMORROW})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "Absent" and body["pdf_url"].startswith("/api/pdf/faculty/")
    assert (config.REPORTS_DIR / "faculty" / "faculty_report_0001.pdf").exists()
    assert instructor.get(body["pdf_url"]).status_code == 200
    assert admin.get(body["pdf_url"]).status_code == 200
    assert student.get(body["pdf_url"]).status_code == 404                   # other users: no

    # students can now ask about the instructor (name comes from the Google account)
    assert "currently unavailable" in student.ask("Is Sir Ines available today?")["answer"]
    check = student.get("/api/faculty/check?name=Ines").json()
    assert check["available"] is False and check["expected_return"] == TOMORROW

    bad = instructor.post("/api/faculty/submit", data={"reason": "x", "start_date": TOMORROW,
                                                       "expected_return": TODAY})
    assert bad.status_code == 400 and "before" in bad.json()["error"]

    assert len(instructor.get("/api/me/faculty").json()["rows"]) == 1
    assert instructor.post("/api/faculty/available").json()["changed"] == 1
    assert "currently recorded as available" in student.ask("Is Sir Ines available today?")["answer"]
    assert admin.get("/api/admin/faculty").json()["rows"][0]["status"] == "Available"


def test_admin_marks_faculty_available(admin, db):
    add_faculty(db, "Someone Else")
    rid = admin.get("/api/admin/faculty").json()["rows"][0]["id"]
    assert admin.post(f"/api/admin/faculty/{rid}/available").status_code == 200
    assert admin.post(f"/api/admin/faculty/{rid}/available").status_code == 400   # already available


# --------------------------------------------------------------- chat / AI
def test_forms_from_chat(student, instructor, admin):
    c = student.ask("The projector in Room 204 is broken.")
    assert c["type"] == "concern_form"
    assert c["prefill"]["room"] == "Room 204" and c["prefill"]["concern_type"] == "Equipment"
    assert instructor.ask("The electric fan is broken")["type"] == "concern_form"
    assert student.ask("I want to give feedback about the library")["type"] == "feedback_form"
    assert student.ask("Can I reserve a laboratory?")["type"] == "message"      # students cannot reserve
    assert instructor.ask("Can I reserve a laboratory?")["type"] == "reservation_form"
    assert admin.ask("Can I reserve a laboratory?")["type"] == "message"     # admins: no student form


def test_campus_info_and_off_topic_never_use_llm(student, prompts):
    assert "Library is near CAS" in student.ask("Where is the library?")["answer"]
    assert "1st Canteen" in student.ask("Which canteen is near the CBM area?")["answer"]
    assert student.ask("What is Python?")["answer"] == OFF_TOPIC_RESPONSE
    assert prompts == []


def test_llm_gets_only_the_role(student, instructor, admin, prompts):
    assert student.ask("Can students use the gym?")["answer"] == "MODEL ANSWER"
    assert "Current user role: student" in prompts[-1]
    assert "sam@nemsu.edu.ph" not in prompts[-1] and "Sam Student" not in prompts[-1]
    instructor.ask("Can instructors use the gym?")
    assert "Current user role: instructor" in prompts[-1]
    admin.ask("Is the gym open to everyone?")
    assert "Current user role: admin" in prompts[-1]


def test_privacy_in_chat(student, student2):
    assert "can't share private" in student.ask("What is Alex's email address?")["answer"]
    assert "sam@nemsu.edu.ph" in student.ask("What is my email?")["answer"]
    assert "student" in student.ask("What is my role?")["answer"]


def test_home_counts_and_unknown_kind(student):
    student.post("/api/concerns", data=concern_form())
    assert student.get("/api/home").json()["counts"]["concerns"] == 1
    assert student.get("/api/me/records/nonsense").status_code == 404


def test_other_campus_gets_google_map_card(student):
    r = student.ask("Where is Bislig campus?")
    assert r["type"] == "map"
    assert r["map"]["title"] == "NEMSU Bislig Campus"
    assert "output=embed" in r["map"]["embed_url"]
    assert "8.2474349,126.2751908" in r["map"]["url"]
    # Tandag still gets its own map
    t = student.ask("where is nemsu")
    assert t["type"] == "map" and "9.0394399" in t["map"]["url"]


def test_campus_places_get_map_cards(student):
    def ask(q):
        return student.post("/api/ask", json={"question": q}).json()
    r = ask("Where is the library?")
    assert r["type"] == "map" and r["map"]["title"] == "Library"
    assert "output=embed" in r["map"]["embed_url"]
    assert ask("map of the 2nd canteen")["map"]["title"] == "2nd Canteen"
    assert ask("where is the gate")["type"] == "message"        # asks which gate
    assert ask("what time does the library open")["type"] != "map"


def test_pdf_is_rebuilt_when_the_server_lost_the_file(admin, student):
    """Render wipes the disk on every deploy; the admin must still open the PDF."""
    from app.services import concern_service
    body = student.post("/api/concerns", data=concern_form()).json()
    concern_service.pdf_path(body["id"]).unlink()                 # simulate a redeploy
    r = admin.get(body["pdf_url"])
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


def test_available_rooms_question_lists_real_rooms(admin, student):
    admin.post("/api/admin/rooms", json={"room_id": "CBM-101", "name": "CBM Room 101",
                                         "building": "CBM Building", "capacity": "40",
                                         "status": "Available"})
    r = student.ask("available rooms in cbm")
    assert r["type"] == "message" and "CBM Room 101" in r["answer"]
    r = student.ask("what are available rooms?")
    assert "CBM Room 101" in r["answer"]


def test_admin_announcements_feed_the_ai(admin, student):
    assert student.post("/api/admin/announcements", json={}).status_code in (401, 403)
    ok = admin.post("/api/admin/announcements", json={
        "title": "Local MAST starts October 20", "category": "Event",
        "body": "The Local MAST opens on October 20 at the gymnasium. All students are invited."})
    assert ok.status_code == 200, ok.text
    admin.post("/api/admin/announcements", json={
        "title": "Intramurals Champions", "category": "Champions",
        "body": "CBM won the overall championship this year."})
    admin.post("/api/admin/announcements", json={
        "title": "Old news", "category": "News", "body": "This one already ended.",
        "start_date": "2020-01-01", "end_date": "2020-01-31"})
    assert admin.post("/api/admin/announcements", json={
        "title": "x", "category": "Nope", "body": "y"}).status_code == 400
    # a broad question lists the active ones only
    a = student.ask("Any announcements?")["answer"]
    assert "Local MAST" in a and "Intramurals Champions" in a and "Old news" not in a
    # a category question filters
    c = student.ask("Who are the champions?")["answer"]
    assert "CBM won" in c and "Local MAST" not in c
    # a free question is matched without the language model
    m = student.ask("When does the local mast start?")["answer"]
    assert "October 20" in m
    assert [r["title"] for r in student.get("/api/announcements").json()["rows"]] \
        == ["Intramurals Champions", "Local MAST starts October 20"]


def test_lost_items_and_plain_concerns_from_chat(student, admin):
    lost = student.ask("i loss my phone")                       # typo of "lost"
    assert lost["type"] == "report_form"
    assert lost["prefill"]["report_type"] == "Lost & Found"
    assert student.ask("nawala akong payong")["type"] == "report_form"
    assert student.ask("i found an id in the library")["type"] == "report_form"
    assert admin.ask("i lost my wallet")["type"] == "message"   # admins: no student form
    assert student.ask("i am lost")["type"] != "report_form"    # no item -> not a lost item

    c = student.ask("i have concern in the cite cr")            # no "report"/"broken" word
    assert c["type"] == "concern_form"
    assert c["prefill"]["location"] == "CITE / ICT area"
    assert c["prefill"]["concern_type"] == "Plumbing"
    assert student.ask("i have concern in cite toilet")["type"] == "concern_form"


# ---------------------------------------------------------- "Other" type text
def test_other_type_needs_typed_text(student):
    base = concern_form(concern_type="Other")
    r = student.post("/api/concerns", data=base)
    assert r.status_code == 400                                   # "Other" with nothing typed
    r = student.post("/api/concerns", data={**base, "concern_type_other": "Broken clock"})
    assert r.status_code == 200
    rows = student.get("/api/me/records/concerns").json()["rows"]
    assert rows[0]["concern_type"] == "Other: Broken clock"

    rep = {"location": "Gate", "report_type": "Other", "report_type_other": "Stray dog",
           "description": "Dog near gate", "report_date": TODAY}
    assert student.post("/api/reports", data=rep).status_code == 200
    fb = {"area": "Library", "feedback_type": "Other", "feedback_type_other": "Question",
          "message": "Hello", "feedback_date": TODAY}
    assert student.post("/api/feedback", data=fb).status_code == 200
    assert student.post("/api/feedback", data={**fb, "feedback_type_other": ""}).status_code == 400


# ------------------------------------------------------------- chat history
def test_chat_history_is_saved_and_reopened_after_logout(student):
    a = student.post("/api/ask", json={"question": "Where is the library?"}).json()
    sid = a["session_id"]
    b = student.post("/api/ask", json={"question": "Which canteen is near the CBM area?",
                                       "session_id": sid}).json()
    assert b["session_id"] == sid                               # same conversation
    chats = student.get("/api/chats").json()
    assert [c["id"] for c in chats["chats"]] == [sid] and chats["keep_days"] == 3
    assert chats["chats"][0]["title"] == "Where is the library?"

    # sign out and in again: the history is still there
    student.post("/api/auth/logout")
    opened = type(student)()
    opened.google_login("sam@nemsu.edu.ph", "Sam Student")
    chat = opened.get(f"/api/chats/{sid}").json()
    assert [m["role"] for m in chat["messages"]] == ["user", "ai", "user", "ai"]
    assert "Library" in chat["messages"][1]["text"]


def test_chat_history_is_private_and_deletable(student, student2):
    sid = student.post("/api/ask", json={"question": "Where is the library?"}).json()["session_id"]
    assert student2.get("/api/chats").json()["chats"] == []
    assert student2.get(f"/api/chats/{sid}").status_code == 400          # not theirs
    assert student2.delete(f"/api/chats/{sid}").status_code == 400
    # a stolen session id just starts a new chat for the other person
    other = student2.post("/api/ask", json={"question": "Hi", "session_id": sid}).json()["session_id"]
    assert other != sid
    assert student.delete(f"/api/chats/{sid}").status_code == 200
    assert student.get("/api/chats").json()["chats"] == []
    student.post("/api/ask", json={"question": "Where is the library?"})
    assert student.delete("/api/chats").status_code == 200
    assert student.get("/api/chats").json()["chats"] == []


def test_old_chats_are_deleted_automatically(student, db):
    from datetime import datetime, timedelta
    from app.models import ChatMessage, ChatSession
    old = student.post("/api/ask", json={"question": "Where is the library?"}).json()["session_id"]
    fresh = student.post("/api/ask", json={"question": "Which canteen is near the CBM area?"}).json()["session_id"]
    stale = datetime.now() - timedelta(days=3, hours=1)
    row = db.get(ChatSession, old)
    row.updated_at = row.created_at = stale
    for m in db.query(ChatMessage).filter(ChatMessage.session_id == old):
        m.created_at = stale
    db.commit()
    ids = [c["id"] for c in student.get("/api/chats").json()["chats"]]
    assert ids == [fresh]                                                # the 3-day-old chat is gone
    db.expire_all()
    assert db.get(ChatSession, old) is None
    assert db.query(ChatMessage).filter(ChatMessage.session_id == old).count() == 0


# ------------------------------------------------------- sentiment analysis
def test_sentiment_analyzer_examples():
    from app.services.sentiment_service import analyze
    assert analyze("The staff were very helpful, thank you!")["label"] == "Positive"
    assert analyze("The projector is broken and the room is dirty.")["label"] == "Negative"
    assert analyze("Not bad")["label"] == "Positive"                       # negation flips
    assert analyze("This is not good")["label"] == "Negative"
    assert analyze("Where is the library?")["label"] == "Neutral"
    assert analyze("Maayo ang library, salamat kaayo")["label"] == "Positive"   # Bisaya
    assert analyze("Sira ang aircon, sobrang init")["label"] == "Negative"      # Tagalog
    assert analyze("Friendly staff but the room is very dirty and noisy")["label"] == "Negative"
    assert analyze("Friendly and helpful staff but slow and dirty rooms, terrible smell")["label"] in ("Mixed", "Negative")
    assert -100 <= analyze("worst terrible awful")["score"] < 0


def test_sentiment_saved_and_admin_only(student, admin):
    fb = {"area": "Library", "feedback_type": "Compliment", "feedback_date": TODAY,
          "message": "The librarian was very helpful, thank you!"}
    assert student.post("/api/feedback", data=fb).status_code == 200
    student.post("/api/feedback", data={**fb, "feedback_type": "Complaint",
                                        "message": "The aircon is broken and the room is dirty."})
    student.post("/api/concerns", data=concern_form(description="The door is not working."))

    rows = admin.get("/api/admin/records/feedback").json()
    by_label = {r["sentiment"] for r in rows["rows"]}
    assert by_label == {"Positive", "Negative"}
    assert ["Sentiment", "sentiment"] in rows["columns"]
    only_neg = admin.get("/api/admin/records/feedback?sentiment=Negative").json()["rows"]
    assert len(only_neg) == 1 and only_neg[0]["sentiment"] == "Negative"

    d = admin.get("/api/admin/dashboard").json()
    assert dict((k, v) for k, v in d["stats"])["Negative Feedback"] == 1
    assert d["charts"]["feedback_sentiment"]["total"] == 2
    assert len(d["negative_feedback"]) == 1

    mine = student.get("/api/me/records/feedback").json()                  # students never see it
    assert all("sentiment" not in r for r in mine["rows"])
    assert ["Sentiment", "sentiment"] not in mine["columns"]


def test_sentiment_backfill_for_old_rows(student, db):
    from app.models import Feedback
    from app.services import sentiment_service
    student.post("/api/feedback", data={"area": "Library", "feedback_type": "Other", "feedback_type_other": "x",
                                        "feedback_date": TODAY, "message": "Terrible, dirty and rude staff"})
    row = db.query(Feedback).first()
    row.sentiment = row.sentiment_score = None
    db.commit()
    sentiment_service.backfill(db)
    db.refresh(row)
    assert row.sentiment == "Negative" and row.sentiment_score < 0


# --------------------------------------------- everyday wording (Bisaya / Tagalog / English)
def test_find_my_phone_opens_the_lost_and_found_form(student):
    for text in ["can you help me find my phone?", "nawala akong cellphone", "asa ang akong wallet",
                 "I can't find my bag", "hinahanap ko ang payong ko"]:
        a = student.ask(text)
        assert a["type"] == "report_form", text
        assert a["prefill"]["report_type"] == "Lost & Found"
    assert student.ask("What is the phone number of the registrar?")["type"] != "report_form"


def test_about_the_assistant_and_local_greetings(student):
    assert "NEMSAI" in student.ask("taga asa ka?")["answer"]
    assert "NEMSAI" in student.ask("what is your name?")["answer"]
    assert "NEMSAI" in student.ask("kumusta")["answer"]
    assert "NEMSAI" in student.ask("maayong buntag")["answer"]


def test_where_is_it_follow_up_uses_the_chat(student):
    sid = student.post("/api/ask", json={"question": "asa ang cite?"}).json()["session_id"]
    a = student.post("/api/ask", json={"question": "asa dapit na?", "session_id": sid}).json()
    assert "ICT area" in a["answer"] and "OFF" not in a["answer"].upper()[:3]
    # with no earlier question there is nothing to refer to
    assert student.ask("asa dapit na?")["answer"] != a["answer"]
