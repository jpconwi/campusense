"""
models.py - PostgreSQL tables.

users, admin_credentials, concerns, reports, feedback, reservations,
faculty_reports, rooms, campus_info, announcements, knowledge_documents.

(Faculty availability, rooms and campus information used to be CSV files.
They are normal tables now, so every part of the system reads one database.)
"""

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
                        Integer, String, Text, Time, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now():
    return datetime.now().replace(microsecond=0)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('student','instructor','admin')", name="users_role_check"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    last_login: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AdminCredential(Base):
    __tablename__ = "admin_credentials"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class Concern(Base):
    __tablename__ = "concerns"
    __table_args__ = (Index("idx_concerns_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reporter_name: Mapped[str] = mapped_column(String(200), nullable=False)
    reporter_email: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    room: Mapped[Optional[str]] = mapped_column(String(60))
    concern_type: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    concern_date: Mapped[date] = mapped_column(Date, nullable=False)
    image_filename: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="Pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (Index("idx_reports_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reporter_name: Mapped[str] = mapped_column(String(200), nullable=False)
    reporter_email: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    area: Mapped[Optional[str]] = mapped_column(String(120))
    room: Mapped[Optional[str]] = mapped_column(String(60))
    report_type: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    image_filename: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="Pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (Index("idx_feedback_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    area: Mapped[str] = mapped_column(String(120), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(60), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    feedback_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="Pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        Index("idx_reservations_user", "user_id"),
        Index("idx_reservations_slot", "facility", "reservation_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    requester_name: Mapped[str] = mapped_column(String(200), nullable=False)
    requester_email: Mapped[str] = mapped_column(String(255), nullable=False)
    facility: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(String(300), nullable=False)
    reservation_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    additional_info: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="Pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class FacultyReport(Base):
    """Instructor absence reports. The AI answers availability questions from this table."""
    __tablename__ = "faculty_reports"
    __table_args__ = (Index("idx_faculty_email", "instructor_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instructor: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_return: Mapped[date] = mapped_column(Date, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="Absent", nullable=False)
    instructor_email: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    building: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    room_type: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    capacity: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    equipment: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="", nullable=False)


class CampusInfo(Base):
    """Question/answer facts the AI uses before it ever calls the language model."""
    __tablename__ = "campus_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String(80), nullable=False)
    keywords: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str] = mapped_column(String(2000), nullable=False)


class Announcement(Base):
    """News the admin feeds to the AI: announcements, events, champions, updates."""
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(30), default="Announcement", nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)   # show from
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)     # show until
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class KnowledgeDocument(Base):
    """One public NEMSU document (news article, memorandum, later Facebook post, PDF...).

    This is the knowledge base the RAG step will search. `source_url` is unique so the
    same announcement is never stored twice. `source_type` says where it came from:
    nemsu_news, nemsu_memo (later: facebook, pdf).
    """
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False, unique=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    author: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now,
                                                 nullable=False)


# Topics are unique ignoring upper/lower case.
Index("uq_campus_topic_lower", func.lower(CampusInfo.topic), unique=True)