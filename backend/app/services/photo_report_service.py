"""
services/photo_report_service.py - the photo report flow.

  1. analyze()  the student sends a photo (+ optional description). The photo is saved, an unsent
                DRAFT is kept (administrators never see drafts) and the AI checks it.
                The student can answer follow-up questions and check again.
  2. submit()   the draft becomes a normal row in `reports` (source = "photo") that shows up on the
                administrator's dashboard with the photo, the student's own words, the AI notes,
                the category, the location (if given) and the submission details.
  3. verify()   an administrator confirms or rejects the AI findings. Until then they are shown as
                "Unverified".
"""

import json
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import config
from app.models import PhotoDraft, Report
from app.services import common, image_analysis_service as ias, sentiment_service
from app.services.common import ValidationError, clean_text, now
from app.services.pdf_service import ensure_pdf
from app.services.report_service import pdf_path
from app.services.upload_service import save_image

VERIFICATION_STATES = ["Unverified", "Confirmed", "Not confirmed"]


def _remove_file(filename):
    try:
        if filename:
            (config.UPLOAD_DIR / filename).unlink(missing_ok=True)
    except OSError:
        pass


def _fields(form):
    """Clean the optional text fields. None = the browser did not send this field (keep old value)."""
    out = {}
    for key, label, size in (("description", "Description", 2000), ("location", "Location", 120),
                             ("noticed_when", "When you noticed it", 120),
                             ("observed_cause", "Cause", 500)):
        if form.get(key) is not None:
            out[key] = clean_text(form.get(key), label, size, required=False)
    return out


def _own_draft(db, user, draft_id):
    draft = db.get(PhotoDraft, draft_id) if draft_id else None
    if draft is None or draft.user_id != user.id:
        raise ValidationError("That photo report was not found. It may have expired - please send the photo again.")
    return draft


def _check(db, draft):
    """Run the AI on the draft and store the result."""
    analysis, provider = ias.analyze(config.UPLOAD_DIR / draft.image_filename, draft.description or "",
                                     draft.location or "", draft.noticed_when or "", draft.observed_cause or "")
    draft.analysis = json.dumps(analysis)
    draft.ai_provider = provider
    draft.checks += 1
    draft.updated_at = now()
    db.commit()
    return analysis


def _loaded(draft):
    return json.loads(draft.analysis) if draft.analysis else None


def _response(draft, analysis):
    description = draft.description or ""
    questions = ias.follow_up_questions(analysis, description, draft.location, draft.noticed_when,
                                        draft.observed_cause)
    return {
        "draft_id": draft.id,
        "outcome": ias.outcome(analysis, description),
        "can_submit": ias.can_submit(analysis, description),
        "message": ias.student_message(analysis, description, questions),
        "questions": questions,
        "analysis": ias.public_view(analysis),
        "values": {"description": draft.description or "", "location": draft.location or "",
                   "noticed_when": draft.noticed_when or "", "observed_cause": draft.observed_cause or ""},
        "checks_left": max(0, ias.MAX_CHECKS_PER_DRAFT - draft.checks),
    }


def analyze(db: Session, user, form, image_file, draft_id=None):
    """First check (needs a photo) or a re-check after the student added information (draft_id)."""
    values = _fields(form)
    if draft_id:
        draft = _own_draft(db, user, draft_id)
        if draft.checks >= ias.MAX_CHECKS_PER_DRAFT:
            raise ValidationError("You've checked this photo several times already. "
                                  "Please send the report now, or start a new one.")
    else:
        filename = save_image(image_file)
        if not filename:
            raise ValidationError("Please choose or take a photo first.")
        draft = PhotoDraft(user_id=user.id, image_filename=filename, checks=0,
                           created_at=now(), updated_at=now())
        db.add(draft)
    for key, value in values.items():
        setattr(draft, key, value or None)
    db.commit()
    return _response(draft, _check(db, draft))


def discard(db: Session, user, draft_id):
    draft = _own_draft(db, user, draft_id)
    _remove_file(draft.image_filename)
    db.delete(draft)
    db.commit()


def submit(db: Session, user, draft_id, form):
    draft = _own_draft(db, user, draft_id)
    for key, value in _fields(form).items():
        setattr(draft, key, value or None)
    description = draft.description or ""

    analysis = _loaded(draft)
    stale = analysis is None or analysis.get("description_hash") != ias.description_hash(description)
    if stale and draft.checks < ias.MAX_CHECKS_PER_DRAFT:
        analysis = _check(db, draft)            # the text changed: check the photo against the final text
    elif analysis is None:
        raise ValidationError("Please let me check the photo first.")
    elif stale:
        analysis["description_changed_after_check"] = True

    if not ias.can_submit(analysis, description):
        raise ValidationError("I can't send this yet. Please tell me what you would like to report.")

    state = ias.outcome(analysis, description)
    stamp = now()
    real_text = description.strip()
    mood = sentiment_service.analyze(real_text) if real_text else {"label": "Neutral", "score": 0}
    report = Report(
        user_id=user.id, reporter_name=user.name, reporter_email=user.email,
        location=draft.location or ias.NOT_PROVIDED, report_type=analysis["category"] if state == "issue" else "Other",
        description=real_text or ias.NO_DESCRIPTION, report_date=stamp.date(),
        image_filename=draft.image_filename, status="Pending",
        sentiment=mood["label"], sentiment_score=mood["score"], created_at=stamp, updated_at=stamp,
        source="photo", ai_status=analysis.get("status"), ai_analysis=json.dumps(analysis),
        ai_provider=draft.ai_provider, urgent=bool(analysis.get("urgent")),
        noticed_when=draft.noticed_when, observed_cause=draft.observed_cause, verification="Unverified")
    db.add(report)
    db.delete(draft)
    db.commit()

    row = common.get_row(db, "reports", report.id)
    try:
        ensure_pdf("reports", row, pdf_path(report.id))
    except Exception as error:                  # the PDF is a bonus, never lose the report
        print("PHOTO REPORT PDF ERROR:", repr(error)[:200])
    return row


def purge_old_drafts(db: Session):
    limit = now() - timedelta(hours=config.PHOTO_DRAFT_HOURS)
    old = db.execute(select(PhotoDraft).where(PhotoDraft.updated_at < limit)).scalars().all()
    for draft in old:
        _remove_file(draft.image_filename)
    if old:
        db.execute(delete(PhotoDraft).where(PhotoDraft.id.in_([d.id for d in old])))
        db.commit()
    return len(old)


def purge_old_drafts_safely():
    from app.database import SessionLocal
    try:
        with SessionLocal() as db:
            purge_old_drafts(db)
    except Exception as error:                  # pragma: no cover
        print("PHOTO DRAFT CLEANUP ERROR:", repr(error))


# ---------------------------------------------------------------- administrators
def verify(db: Session, admin, report_id, verification, note=""):
    if verification not in VERIFICATION_STATES:
        raise ValidationError("Invalid verification.")
    row = db.get(Report, report_id)
    if row is None or row.source != "photo":
        raise ValidationError("Photo report not found.")
    row.verification = verification
    row.verification_note = clean_text(note, "Note", 500, required=False) or None
    row.verified_by = admin.email if verification != "Unverified" else None
    row.verified_at = now() if verification != "Unverified" else None
    row.updated_at = now()
    db.commit()


def for_admin(row):
    """Row dict for the admin pages: the AI JSON becomes a real object under row["ai"]."""
    data = dict(row)
    raw = data.pop("ai_analysis", None)
    try:
        data["ai"] = json.loads(raw) if raw else None
    except ValueError:
        data["ai"] = None
    return data


def for_student(row):
    """Rows shown to the student who sent them: no administrator notes, no raw AI data."""
    return {k: v for k, v in row.items()
            if k not in ("ai_analysis", "verification_note", "verified_by", "verified_at", "ai_provider")}
