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
    _add_student_registration_columns()
    _widen_campus_info_columns()
    _add_sentiment_columns()
    _add_photo_report_columns()
    from app.services import campus_service, sentiment_service
    with SessionLocal() as db:
        campus_service.seed_if_empty(db)
        sentiment_service.backfill(db)


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
        "student_id": "VARCHAR(50)",
        "verification_document": binary_type,
        "verification_content_type": "VARCHAR(100)",
        "verification_filename": "VARCHAR(255)",
    }
    with engine.begin() as conn:
        for name, kind in additions.items():
            if engine.dialect.name == "postgresql":
                conn.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {name} {kind}"))
            elif name not in columns:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {kind}"))


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
