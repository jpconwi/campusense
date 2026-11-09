"""
database.py - PostgreSQL connection (SQLAlchemy 2.0) and the per-request session.

The tables are defined in models.py. `init_db()` creates any missing table when
the app starts. (For schema changes later, add Alembic migrations.)
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app import config

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=10)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: one database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create the tables if they do not exist yet, then seed campus information."""
    from app import models  # noqa: F401  (registers the tables)
    Base.metadata.create_all(engine)
    _allow_super_admin_role()
    _add_student_registration_columns()
    _add_help_message_category()
    _widen_campus_info_columns()
    _add_sentiment_columns()
    _add_photo_report_columns()
    _add_photo_concern_columns()
    _add_photo_draft_session_column()
    _add_report_assignment_column()
    _add_report_workflow_review_columns()
    _add_feedback_routing_columns()
    _add_faculty_reservation_review_columns()
    from app.services import campus_service, sentiment_service
    with SessionLocal() as db:
        from app.model import systemAi
        from app.models import AIProviderSetting
        for setting in db.query(AIProviderSetting).all():
            systemAi.set_provider_enabled(setting.provider, setting.enabled)
        campus_service.seed_if_empty(db)
        sentiment_service.backfill(db)


def _allow_super_admin_role():
    """Widen the existing PostgreSQL role check while keeping old databases usable."""
    if engine.dialect.name != "postgresql":
        return
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check"))
        conn.execute(text("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('student','instructor','admin','super_admin'))"))


def _widen_campus_info_columns():
    """create_all() never alters an existing table, so widen the old
    varchar(200)/varchar(600) columns on databases created before the change.
    Safe to run on every start (widening to the same size is a no-op)."""
    if engine.dialect.name != "postgresql":
        return
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE campus_info ALTER COLUMN keywords TYPE VARCHAR(500)"))
        conn.execute(text("ALTER TABLE campus_info ALTER COLUMN answer TYPE VARCHAR(2000)"))


def _add_student_registration_columns():
    """Add account review and private verification-file fields to existing databases."""
    from sqlalchemy import inspect, text
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    binary_type = "BYTEA" if engine.dialect.name == "postgresql" else "BLOB"
    additions = {
        "approval_status": "VARCHAR(20) NOT NULL DEFAULT 'Approved'",
        "registration_type": "VARCHAR(20)",
        "student_id": "VARCHAR(50)",
        "department": "VARCHAR(120)",
        "verification_document": binary_type,
        "verification_content_type": "VARCHAR(100)",
        "verification_filename": "VARCHAR(255)",
        "verification_document_kind": "VARCHAR(20)",
        "verification_cor_document": binary_type,
        "verification_cor_content_type": "VARCHAR(100)",
        "verification_cor_filename": "VARCHAR(255)",
        "verification_id_back_document": binary_type,
        "verification_id_back_content_type": "VARCHAR(100)",
        "verification_id_back_filename": "VARCHAR(255)",
        "verification_ai_note": "TEXT",
        "face_image": binary_type,
        "face_image_content_type": "VARCHAR(100)",
        "face_image_filename": "VARCHAR(255)",
        "face_scan_pdf": binary_type,
        "face_scan_pdf_filename": "VARCHAR(255)",
        "face_review_status": "VARCHAR(20) NOT NULL DEFAULT 'Not required'",
        "review_status": "VARCHAR(20) NOT NULL DEFAULT 'Unreviewed'",
        "reviewed_by": "VARCHAR(255)",
        "reviewed_at": "TIMESTAMP",
        "review_note": "VARCHAR(500)",
        "rejection_reason": "VARCHAR(300)",
        "deleted_at": "TIMESTAMP",
        "purge_after": "TIMESTAMP",
    }
    with engine.begin() as conn:
        for name, kind in additions.items():
            if engine.dialect.name == "postgresql":
                conn.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {name} {kind}"))
            elif name not in columns:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {kind}"))


def _add_help_message_category():
    """Add message categories to the existing applicant help inbox table."""
    from sqlalchemy import inspect, text
    if "registration_help_messages" not in inspect(engine).get_table_names():
        return
    columns = {column["name"] for column in inspect(engine).get_columns("registration_help_messages")}
    if "category" in columns:
        return
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE registration_help_messages ADD COLUMN category VARCHAR(40) NOT NULL DEFAULT 'Registration'"))
        else:
            conn.execute(text("ALTER TABLE registration_help_messages ADD COLUMN category VARCHAR(40) NOT NULL DEFAULT 'Registration'"))


def _add_sentiment_columns():
    """create_all() never alters an existing table, so add the sentiment columns to
    databases created before sentiment analysis existed. Safe to run on every start."""
    if engine.dialect.name != "postgresql":
        return
    from sqlalchemy import text
    with engine.begin() as conn:
        for table in ("concerns", "reports", "feedback"):
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS sentiment VARCHAR(10)"))
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS sentiment_score INTEGER"))


def _add_photo_report_columns():
    """Add the photo-report columns to a `reports` table created before photo reports existed.
    Safe to run on every start."""
    if engine.dialect.name != "postgresql":
        return
    from sqlalchemy import text
    columns = [
        ("source", "VARCHAR(10) NOT NULL DEFAULT 'form'"), ("ai_status", "VARCHAR(15)"),
        ("ai_analysis", "TEXT"), ("ai_provider", "VARCHAR(80)"),
        ("urgent", "BOOLEAN NOT NULL DEFAULT FALSE"), ("noticed_when", "VARCHAR(120)"),
        ("observed_cause", "VARCHAR(500)"), ("verification", "VARCHAR(20)"),
        ("verification_note", "VARCHAR(500)"), ("verified_by", "VARCHAR(255)"),
        ("verified_at", "TIMESTAMP"),
    ]
    with engine.begin() as conn:
        for name, kind in columns:
            conn.execute(text(f"ALTER TABLE reports ADD COLUMN IF NOT EXISTS {name} {kind}"))


def _add_photo_concern_columns():
    """Keep AI assisted photo concerns reviewable in the normal concerns inbox."""
    from sqlalchemy import inspect, text
    columns = [
        ("source", "VARCHAR(10) NOT NULL DEFAULT 'form'"), ("ai_status", "VARCHAR(15)"),
        ("ai_analysis", "TEXT"), ("ai_provider", "VARCHAR(80)"),
        ("noticed_when", "VARCHAR(120)"), ("observed_cause", "VARCHAR(500)"),
    ]
    existing = {column["name"] for column in inspect(engine).get_columns("concerns")}
    with engine.begin() as conn:
        for name, kind in columns:
            if engine.dialect.name == "postgresql":
                conn.execute(text(f"ALTER TABLE concerns ADD COLUMN IF NOT EXISTS {name} {kind}"))
            elif name not in existing:
                conn.execute(text(f"ALTER TABLE concerns ADD COLUMN {name} {kind}"))


def _add_photo_draft_session_column():
    """Associate an unfinished photo draft with its chat where possible."""
    from sqlalchemy import inspect, text
    if "photo_drafts" not in inspect(engine).get_table_names():
        return
    columns = {column["name"] for column in inspect(engine).get_columns("photo_drafts")}
    if "session_id" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE photo_drafts ADD COLUMN session_id INTEGER"))


def _add_report_assignment_column():
    """Add report assignment and reporter-facing admin update fields."""
    from sqlalchemy import inspect, text
    tables = {"reports": {column["name"] for column in inspect(engine).get_columns("reports")},
              "concerns": {column["name"] for column in inspect(engine).get_columns("concerns")}}
    with engine.begin() as conn:
        for table in ("reports", "concerns"):
            for column, sql_type in (("assigned_admin_email", "VARCHAR(255)"), ("admin_feedback", "TEXT")):
                if column in tables[table]:
                    continue
                if engine.dialect.name == "postgresql":
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type}"))
                else:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
        if engine.dialect.name == "postgresql":
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_assigned_admin_email ON reports (assigned_admin_email)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_concerns_assigned_admin_email ON concerns (assigned_admin_email)"))


def _add_report_workflow_review_columns():
    """Add the Super Admin intake decision fields to reports and concerns."""
    from sqlalchemy import inspect, text
    tables = {table: {column["name"] for column in inspect(engine).get_columns(table)}
              for table in ("reports", "concerns")}
    additions = {
        "workflow_review": "VARCHAR(20) NOT NULL DEFAULT 'Pending'",
        "workflow_review_note": "VARCHAR(500)",
        "workflow_reviewed_by": "VARCHAR(255)",
        "workflow_reviewed_at": "TIMESTAMP",
    }
    with engine.begin() as conn:
        for table, columns in tables.items():
            for name, sql_type in additions.items():
                if name in columns:
                    continue
                if engine.dialect.name == "postgresql":
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {sql_type}"))
                else:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def _add_feedback_routing_columns():
    """Add feedback routing, response, and forwarding fields to existing databases."""
    from sqlalchemy import inspect, text
    columns = {column["name"] for column in inspect(engine).get_columns("feedback")}
    binary = "BOOLEAN NOT NULL DEFAULT FALSE"
    additions = {
        "feedback_scope": "VARCHAR(20) NOT NULL DEFAULT 'campus'",
        "admin_response": "TEXT",
        "forwarded_to_super_admin": binary,
        "forwarded_by": "VARCHAR(255)",
        "forwarded_at": "TIMESTAMP",
    }
    with engine.begin() as conn:
        for name, sql_type in additions.items():
            if name in columns:
                continue
            if engine.dialect.name == "postgresql":
                conn.execute(text(f"ALTER TABLE feedback ADD COLUMN IF NOT EXISTS {name} {sql_type}"))
            else:
                conn.execute(text(f"ALTER TABLE feedback ADD COLUMN {name} {sql_type}"))


def _add_faculty_reservation_review_columns():
    """Add reviewer audit fields; preserve old faculty reports as reviewed."""
    from sqlalchemy import inspect, text
    tables = {
        table: {column["name"] for column in inspect(engine).get_columns(table)}
        for table in ("faculty_reports", "reservations")
    }
    additions = {
        "faculty_reports": {
            "review_status": "VARCHAR(20) NOT NULL DEFAULT 'Approved'",
            "reviewed_by": "VARCHAR(255)",
            "reviewed_at": "TIMESTAMP",
            "review_note": "VARCHAR(500)",
        },
        "reservations": {
            "reviewed_by": "VARCHAR(255)",
            "reviewed_at": "TIMESTAMP",
            "review_note": "VARCHAR(500)",
        },
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            for column, sql_type in columns.items():
                if engine.dialect.name == "postgresql":
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type}"))
                elif column not in tables[table]:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
