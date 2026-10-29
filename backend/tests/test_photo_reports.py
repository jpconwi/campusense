"""Photo reports: upload -> AI check (faked) -> follow-up questions -> admin dashboard -> verification."""

import io
import json

import pytest
from PIL import Image

from app import config
from app.model import systemAi
from app.models import PhotoDraft, Report
from app.services import photo_report_service


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 90, 60)).save(buf, "PNG")
    return buf.getvalue()


IMG = ("fix.png", png_bytes(), "image/png")

ISSUE = {"image_kind": "campus_issue", "shows_issue": "yes", "issue_title": "Water leaking from the ceiling",
         "category": "Maintenance", "observations": ["Water stain on the ceiling", "Puddle on the floor"],
         "confidence": "medium", "urgent": False, "urgent_reason": "", "description_check": "supports",
         "description_is_campus_issue": "yes", "check_explanation": "The stain matches the leak described."}


@pytest.fixture
def vision(monkeypatch):
    """Fake vision model. state["reply"] = dict / str / None (None = every provider down)."""
    state = {"reply": dict(ISSUE), "calls": []}

    def fake(system_prompt, user_text, image_b64, mime="image/jpeg"):
        state["calls"].append({"text": user_text, "mime": mime, "len": len(image_b64)})
        reply = state["reply"]
        if reply is None:
            return None, None, None
        return (reply if isinstance(reply, str) else json.dumps(reply)), "huggingface", "fake-vl"

    monkeypatch.setattr(systemAi, "ask_vision", fake)
    return state


def analyze(client, **fields):
    return client.post("/api/reports/photo/analyze", data=fields, files={"image": IMG})


def test_photo_with_description_asks_what_is_missing_then_submits(student, admin, vision, db):
    r = analyze(student, description="The ceiling is leaking in the hallway")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outcome"] == "issue" and body["can_submit"]
    assert {q["key"] for q in body["questions"]} == {"location", "when", "cause"}
    assert "appears to show" in body["message"] and "administrator will check" in body["message"]
    assert "description" in vision["calls"][0]["text"] and vision["calls"][0]["mime"] == "image/jpeg"

    # a draft is NOT a report: the administrator sees nothing yet
    assert admin.get("/api/admin/records/reports").json()["rows"] == []

    sub = student.post(f"/api/reports/photo/{body['draft_id']}/submit",
                       data={"location": "CITE building, 2nd floor", "noticed_when": "this morning",
                             "observed_cause": "pipe above looks old"})
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "Pending"

    rows = admin.get("/api/admin/records/reports").json()["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "photo" and row["report_type"] == "Maintenance"
    assert row["location"] == "CITE building, 2nd floor" and row["noticed_when"] == "this morning"
    assert row["description"] == "The ceiling is leaking in the hallway"      # the student's own words
    assert row["ai"]["issue_title"] == "Water leaking from the ceiling" and row["verification"] == "Unverified"
    assert row["image_filename"] and admin.get(f"/api/uploads/{row['image_filename']}").status_code == 200
    assert admin.get(f"/api/pdf/reports/{row['id']}").status_code == 200       # PDF with photo + AI notes
    assert db.query(PhotoDraft).count() == 0


def test_photo_without_description_gets_follow_up_questions(student, vision):
    vision["reply"].update(description_check="no_description", description_is_campus_issue="no_description")
    body = analyze(student).json()
    keys = [q["key"] for q in body["questions"]]
    assert keys == ["location", "when", "cause", "description"]
    sub = student.post(f"/api/reports/photo/{body['draft_id']}/submit", data={}).json()
    assert sub["success"]
    row = student.get("/api/me/records/reports").json()["rows"][0]
    assert row["location"] == "Not provided" and "did not write a description" in row["description"]


def test_unrelated_image_is_handled_politely_and_not_sent(student, admin, vision, db):
    vision["reply"] = {"image_kind": "meme_or_screenshot", "shows_issue": "no", "confidence": "high",
                       "category": "Other", "observations": [], "urgent": False}
    body = analyze(student).json()
    assert body["outcome"] == "no_issue" and not body["can_submit"] and body["questions"] == []
    assert "doesn't look like a campus problem" in body["message"]
    bad = student.post(f"/api/reports/photo/{body['draft_id']}/submit", data={})
    assert bad.status_code == 400
    assert db.query(Report).count() == 0

    vision["reply"]["image_kind"] = "unrelated"
    assert "couldn't identify a campus issue" in analyze(student).json()["message"]


def test_people_photo_is_not_described(student, vision):
    vision["reply"] = {"image_kind": "people", "shows_issue": "no", "observations": ["two students smiling"]}
    body = analyze(student).json()
    assert "photo of people" in body["message"] and "smiling" not in body["message"]


def test_unclear_photo_asks_for_description(student, vision):
    vision["reply"] = {"image_kind": "unclear", "shows_issue": "unclear", "confidence": "low"}
    body = analyze(student).json()
    assert body["outcome"] == "unclear" and not body["can_submit"]
    assert "describe" in body["message"]


def test_description_that_the_photo_does_not_support_is_flagged_not_dropped(student, admin, vision):
    vision["reply"] = {"image_kind": "campus_no_issue", "shows_issue": "no", "confidence": "medium",
                       "category": "Equipment", "description_check": "contradicts",
                       "description_is_campus_issue": "yes", "observations": ["A clean desk"]}
    body = analyze(student, description="The projector in room 3 is broken").json()
    assert body["outcome"] == "issue" and body["can_submit"]
    assert "can't see what you described" in body["message"]
    student.post(f"/api/reports/photo/{body['draft_id']}/submit", data={})
    row = admin.get("/api/admin/records/reports").json()["rows"][0]
    assert row["ai"]["description_check"] == "contradicts" and row["verification"] == "Unverified"


def test_ai_down_manual_review_still_possible(student, admin, vision):
    vision["reply"] = None
    body = analyze(student).json()
<<<<<<< HEAD
    assert body["outcome"] == "unavailable" and body["can_submit"]       # photo alone can go to an admin
    assert "administrator will review it by hand" in body["message"]
    sent = student.post(f"/api/reports/photo/{body['draft_id']}/submit", data={})
    assert sent.status_code == 200
    assert admin.get("/api/admin/records/reports").json()["rows"][0]["ai_status"] == "unavailable"
=======
    assert body["outcome"] == "unavailable" and not body["can_submit"]
    assert "short description" in body["message"]
>>>>>>> 7b2f77da7aab77f1b933031e132d68de6680299f
    body = analyze(student, description="Broken chair in the library").json()
    assert body["can_submit"]
    student.post(f"/api/reports/photo/{body['draft_id']}/submit", data={})
    row = admin.get("/api/admin/records/reports").json()["rows"][0]
    assert row["ai_status"] == "unavailable" and row["report_type"] == "Other"
<<<<<<< HEAD
    assert row["description"] == "Broken chair in the library"
=======
>>>>>>> 7b2f77da7aab77f1b933031e132d68de6680299f


@pytest.mark.parametrize("garbage", ["I think it is a leak!", "{not json", "[1,2]", ""])
def test_garbage_from_the_model_never_becomes_a_finding(student, vision, garbage):
    vision["reply"] = garbage
    body = analyze(student).json()
    assert body["outcome"] == "unavailable"


def test_model_values_are_checked_against_fixed_lists(student, vision):
    vision["reply"] = dict(ISSUE, category="Hacking", confidence="certain", shows_issue="definitely",
                           observations=["x" * 500] + ["o"] * 20, urgent="maybe")
    a = analyze(student).json()["analysis"]
    assert a["category"] == "Other" and a["confidence"] == "low" and a["shows_issue"] == "unclear"
    assert len(a["observations"]) <= 5 and len(a["observations"][0]) <= 160 and a["urgent"] is False


def test_urgent_hazard_is_flagged_even_if_the_model_misses_it(student, admin, vision):
    body = analyze(student, description="There are exposed wires and sparks near the stairs").json()
    assert body["analysis"]["urgent"] is True and "safety hazard" in body["message"]
    assert "keyword check" in body["analysis"]["urgent_reason"]
    student.post(f"/api/reports/photo/{body['draft_id']}/submit", data={})

    calm = analyze(student, description="Leaking ceiling").json()
    student.post(f"/api/reports/photo/{calm['draft_id']}/submit", data={})
    rows = admin.get("/api/admin/records/reports").json()["rows"]
    assert rows[0]["urgent"] is True and rows[1]["urgent"] is False           # open hazards first
    assert len(admin.get("/api/admin/records/reports?urgent=1").json()["rows"]) == 1
    dash = admin.get("/api/admin/dashboard").json()
    assert ["Urgent Photo Reports (open)", 1] in dash["stats"] and len(dash["urgent_reports"]) == 1


def test_fire_extinguisher_is_not_a_hazard(student, vision):
    body = analyze(student, description="The fire extinguisher is missing its label").json()
    assert body["analysis"]["urgent"] is False


def test_changed_description_is_rechecked_on_submit(student, vision):
    body = analyze(student, description="Leak").json()
    assert len(vision["calls"]) == 1
    student.post(f"/api/reports/photo/{body['draft_id']}/submit", data={"description": "Leak near the CR sink"})
    assert len(vision["calls"]) == 2 and "CR sink" in vision["calls"][1]["text"]


def test_recheck_with_more_info_reuses_the_saved_photo(student, vision, db):
    body = analyze(student, description="Leak").json()
    again = student.post("/api/reports/photo/analyze",
                         data={"draft_id": body["draft_id"], "location": "Library"}).json()
    assert again["draft_id"] == body["draft_id"] and "location" not in [q["key"] for q in again["questions"]]
    assert db.query(PhotoDraft).count() == 1
    for _ in range(10):
        r = student.post("/api/reports/photo/analyze", data={"draft_id": body["draft_id"]})
    assert r.status_code == 400 and "several times" in r.json()["error"]


def test_other_people_cannot_touch_a_draft(student, student2, admin, vision):
    body = analyze(student, description="Leak").json()
    did = body["draft_id"]
    assert student2.post(f"/api/reports/photo/{did}/submit", data={}).status_code == 400
    assert student2.post("/api/reports/photo/analyze", data={"draft_id": did}).status_code == 400
    assert student2.delete(f"/api/reports/photo/{did}").status_code == 400
    assert admin.post(f"/api/reports/photo/{did}/submit", data={}).status_code in (403, 404)


def test_upload_must_be_a_real_image(student, vision):
    r = student.post("/api/reports/photo/analyze", data={"description": "x"},
                     files={"image": ("a.png", b"not an image", "image/png")})
    assert r.status_code == 400
    assert student.post("/api/reports/photo/analyze", data={"description": "x"}).status_code == 400


def test_discard_removes_draft_and_file(student, vision, db):
    body = analyze(student, description="Leak").json()
    name = db.query(PhotoDraft).one().image_filename
    assert (config.UPLOAD_DIR / name).exists()
    assert student.delete(f"/api/reports/photo/{body['draft_id']}").status_code == 200
    assert not (config.UPLOAD_DIR / name).exists() and db.query(PhotoDraft).count() == 0


def test_old_drafts_are_purged(student, vision, db):
    analyze(student, description="Leak")
    draft = db.query(PhotoDraft).one()
    from datetime import timedelta
    draft.updated_at = draft.updated_at - timedelta(hours=config.PHOTO_DRAFT_HOURS + 1)
    db.commit()
    assert photo_report_service.purge_old_drafts(db) == 1 and db.query(PhotoDraft).count() == 0


def test_admin_can_verify_and_students_cannot_see_admin_notes(student, admin, vision):
    body = analyze(student, description="Leak").json()
    student.post(f"/api/reports/photo/{body['draft_id']}/submit", data={})
    rid = admin.get("/api/admin/records/reports").json()["rows"][0]["id"]

    assert student.post(f"/api/admin/reports/{rid}/verify", json={"verification": "Confirmed"}).status_code in (401, 403, 404)
    assert admin.post(f"/api/admin/reports/{rid}/verify", json={"verification": "Maybe"}).status_code == 400
    ok = admin.post(f"/api/admin/reports/{rid}/verify",
                    json={"verification": "Confirmed", "note": "Checked on site, pipe replaced"})
    assert ok.status_code == 200
    row = admin.get("/api/admin/records/reports").json()["rows"][0]
    assert row["verification"] == "Confirmed" and row["verified_by"] == "admin@nemsu.edu.ph"

    mine = student.get("/api/me/records/reports").json()["rows"][0]
    for hidden in ("ai_analysis", "verification_note", "verified_by", "sentiment"):
        assert hidden not in mine
    assert mine["status"] == "Pending"


def test_normal_form_reports_are_unchanged(student, admin):
    r = student.post("/api/reports", data={"location": "Gym", "report_type": "Safety", "description": "Loose rail",
                                           "report_date": __import__("datetime").date.today().isoformat()})
    assert r.status_code == 200
    row = admin.get("/api/admin/records/reports").json()["rows"][0]
    assert row["source"] == "form" and row["urgent"] is False and row["ai"] is None


# ------------------------------------------------------------------ the vision provider chain
def test_vision_chain_falls_back_in_order(monkeypatch):
    for name in ("HUGGINGFACE_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.setattr(config, name, "k")
    for name in ("HF_VISION_MODEL", "OPENROUTER_VISION_MODEL", "GROQ_VISION_MODEL", "GOOGLE_VISION_MODEL"):
        monkeypatch.setattr(config, name, None)
    monkeypatch.setattr(systemAi.time, "sleep", lambda s: None)
    systemAi.reset_cooldowns()
    seen = []

    def callers():
        def make(p):
            def call(model, messages, timeout):
                seen.append((p, model, messages[1]["content"][1]["type"]))
                if p in ("huggingface", "openrouter"):
                    raise RuntimeError("boom")
                return "answer from " + p
            return call
        return {p: make(p) for p in systemAi.VISION_PROVIDER_ORDER}

    monkeypatch.setattr(systemAi, "_vision_callers", callers)
    answer, provider, model = systemAi.ask_vision("sys", "look", "QUJD")
    assert (answer, provider) == ("answer from groq", "groq")
    assert [p for p, _, _ in seen][0] == "huggingface" and all(t == "image_url" for _, _, t in seen)
    systemAi.reset_cooldowns()


def test_vision_without_any_key_returns_nothing(monkeypatch):
    for name in ("HUGGINGFACE_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.setattr(config, name, "")
    assert systemAi.ask_vision("s", "t", "QUJD") == (None, None, None)
<<<<<<< HEAD


def test_vision_models_are_discovered_when_names_change(monkeypatch):
    monkeypatch.setattr(config, "HUGGINGFACE_API_KEY", "k")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    for name in ("HF_VISION_MODEL", "OPENROUTER_VISION_MODEL"):
        monkeypatch.setattr(config, name, None)
    systemAi.reset_cooldowns()

    def fake_get(url, headers):
        if "huggingface" in url:
            return {"data": [{"id": "new/vl-9b", "architecture": {"input_modalities": ["text", "image"]}},
                             {"id": "text/only", "architecture": {"input_modalities": ["text"]}}]}
        return {"data": [
            {"id": "a/free-vl:free", "pricing": {"prompt": "0", "completion": "0"},
             "architecture": {"input_modalities": ["image", "text"]}},
            {"id": "b/paid-vl", "pricing": {"prompt": "0.001", "completion": "0.002"},
             "architecture": {"input_modalities": ["image", "text"]}}]}

    monkeypatch.setattr(systemAi, "_http_get", fake_get)
    assert "new/vl-9b" in systemAi._vision_models("huggingface")
    assert "text/only" not in systemAi._vision_models("huggingface")
    models = systemAi._vision_models("openrouter")
    assert "a/free-vl:free" in models and "b/paid-vl" not in models
    monkeypatch.setattr(config, "HF_VISION_MODEL", "my/model")          # your own choice wins, no discovery
    assert systemAi._vision_models("huggingface") == ["my/model"]
    systemAi.reset_cooldowns()


def test_discovery_failure_keeps_the_defaults(monkeypatch):
    monkeypatch.setattr(config, "HUGGINGFACE_API_KEY", "k")
    monkeypatch.setattr(config, "HF_VISION_MODEL", None)
    systemAi.reset_cooldowns()
    monkeypatch.setattr(systemAi, "_http_get", lambda u, h: (_ for _ in ()).throw(RuntimeError("down")))
    assert systemAi._vision_models("huggingface") == systemAi.DEFAULT_VISION_MODELS["huggingface"]
    systemAi.reset_cooldowns()
=======
>>>>>>> 7b2f77da7aab77f1b933031e132d68de6680299f
