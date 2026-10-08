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


def test_reservation_is_pending_and_validated(student):
    r = student.post("/api/reservations", data=reservation())
    assert r.status_code == 200 and r.json()["status"] == "Pending"
    bad = student.post("/api/reservations", data=reservation(start_time="11:00", end_time="09:00"))
    assert bad.status_code == 400 and "after the start" in bad.json()["error"]
    past = student.post("/api/reservations", data=reservation(reservation_date="2020-01-01"))
    assert past.status_code == 400


def test_admin_approval_and_overlap(student, student2, admin):
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
    assert student.ask("Can I reserve a laboratory?")["type"] == "reservation_form"
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
    r = student.post("/api/ask", json={"question": "Where is Bislig campus?"}).json()
    assert r["type"] == "map"
    assert r["map"]["title"] == "NEMSU Bislig Campus"
    assert "output=embed" in r["map"]["embed_url"]
    assert "8.2474349,126.2751908" in r["map"]["url"]
    # Tandag still gets its own map
    t = student.post("/api/ask", json={"question": "where is nemsu"}).json()
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
