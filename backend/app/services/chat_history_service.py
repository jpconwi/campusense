"""
services/chat_history_service.py - saved chats ("chat history").

* Every question and answer is saved for the signed-in user, so after logging
  out and back in the person can open an earlier chat from the sidebar.
* Chats are deleted AUTOMATICALLY after config.CHAT_HISTORY_DAYS (default 3).
  Cleanup runs at start-up, every hour, and whenever history is read or saved.
* A person can only ever see or delete their own chats.
"""

import json
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import config
from app.models import ChatMessage, ChatSession
from app.services.common import ValidationError

TITLE_LENGTH = 60
_KEEP = ("type", "prefill", "map", "suggestions")      # parts of an answer worth restoring


def _now():
    return datetime.now().replace(microsecond=0)


def cutoff():
    return _now() - timedelta(days=config.CHAT_HISTORY_DAYS)


def purge_old(db: Session):
    """Delete messages older than the retention time, then empty / stale chats."""
    limit = cutoff()
    db.execute(delete(ChatMessage).where(ChatMessage.created_at < limit))
    has_messages = select(ChatMessage.session_id).where(ChatMessage.session_id == ChatSession.id).exists()
    db.execute(delete(ChatSession).where(
        (ChatSession.updated_at < limit) | (~has_messages & (ChatSession.created_at < limit))))
    db.commit()


def purge_old_safely():
    """For the background job and start-up: never crash the app."""
    from app.database import SessionLocal
    try:
        with SessionLocal() as db:
            purge_old(db)
    except Exception as error:                      # pragma: no cover
        print("CHAT CLEANUP ERROR:", repr(error))


def _own_session(db: Session, user_id, session_id):
    row = db.get(ChatSession, session_id) if session_id else None
    if row is None or row.user_id != user_id:
        raise ValidationError("That chat was not found. It may have been deleted after "
                              f"{config.CHAT_HISTORY_DAYS} days.")
    return row


def save_exchange(db: Session, user_id, session_id, question, answer: dict):
    """Save one question + answer. Starts a new chat when session_id is empty or gone."""
    purge_old(db)
    row = None
    if session_id:
        row = db.get(ChatSession, session_id)
        if row is not None and row.user_id != user_id:
            row = None
    stamp = _now()
    if row is None:
        title = " ".join(question.split())[:TITLE_LENGTH] or "New chat"
        row = ChatSession(user_id=user_id, title=title, created_at=stamp, updated_at=stamp)
        db.add(row)
        db.flush()
    payload = {k: answer[k] for k in _KEEP if answer.get(k)}
    db.add(ChatMessage(session_id=row.id, role="user", text=question[:500], created_at=stamp))
    db.add(ChatMessage(session_id=row.id, role="ai", text=str(answer.get("answer") or ""),
                       payload=json.dumps(payload) if payload else None, created_at=stamp))
    row.updated_at = stamp
    db.commit()
    return row.id


def list_chats(db: Session, user_id):
    purge_old(db)
    rows = db.execute(select(ChatSession).where(ChatSession.user_id == user_id)
                      .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())).scalars().all()
    return [{"id": r.id, "title": r.title, "updated_at": r.updated_at.isoformat()} for r in rows]


def get_chat(db: Session, user_id, session_id):
    purge_old(db)
    row = _own_session(db, user_id, session_id)
    messages = db.execute(select(ChatMessage).where(ChatMessage.session_id == row.id)
                          .order_by(ChatMessage.id)).scalars().all()
    out = []
    for m in messages:
        item = {"role": m.role, "text": m.text, "created_at": m.created_at.isoformat()}
        if m.payload:
            try:
                item.update(json.loads(m.payload))
            except ValueError:
                pass
        out.append(item)
    return {"id": row.id, "title": row.title, "messages": out,
            "keep_days": config.CHAT_HISTORY_DAYS}


def delete_chat(db: Session, user_id, session_id):
    row = _own_session(db, user_id, session_id)
    db.delete(row)
    db.commit()


def delete_all(db: Session, user_id):
    ids = select(ChatSession.id).where(ChatSession.user_id == user_id)
    db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(ids)))
    db.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
    db.commit()
