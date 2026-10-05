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
    from app.services import campus_service
    with SessionLocal() as db:
        campus_service.seed_if_empty(db)
