"""
services/user_service.py - user accounts (PostgreSQL).

Stored: Google account ID, name, email, role, dates, active flag.
NOT stored here: passwords (admin password hashes live in admin_credentials), OAuth tokens.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User
from app.services.common import now


def get_user(db: Session, user_id):
    return db.get(User, user_id)


def get_by_email(db: Session, email):
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def get_by_google_id(db: Session, google_id):
    return db.execute(select(User).where(User.google_id == google_id)).scalar_one_or_none()


def login_user(db: Session, google_id, name, email, is_admin):
    """Create the account on first login, update it on later logins."""
    stamp = now()
    existing = get_by_google_id(db, google_id) or get_by_email(db, email)

    if existing is None:
        user = User(google_id=google_id, name=name, email=email,
                    role="admin" if is_admin else None, created_at=stamp, last_login=stamp)
        db.add(user)
        db.commit()
        return user

    # The admin allowlist is the only source of the admin role.
    role = existing.role
    if is_admin:
        role = "admin"
    elif role == "admin":
        role = None          # removed from ADMIN_EMAILS -> must choose again

    existing.google_id, existing.name, existing.email = google_id, name, email
    existing.role, existing.last_login = role, stamp
    db.commit()
    return existing


def login_admin_password(db: Session, email):
    """Admin signed in with email + password. Reuse the account row if the same
    email already exists (e.g. from Google), otherwise create it."""
    stamp = now()
    existing = get_by_email(db, email)
    if existing is None:
        name = email.split("@")[0].replace(".", " ").title()
        user = User(google_id="local-admin:" + email, name=name, email=email, role="admin",
                    created_at=stamp, last_login=stamp)
        db.add(user)
        db.commit()
        return user
    existing.role, existing.last_login = "admin", stamp
    db.commit()
    return existing


def set_role_first_time(db: Session, user_id, role):
    """Save the chosen role only if the user has no role yet."""
    if role not in ("student", "instructor"):
        return False
    user = db.get(User, user_id)
    if user is None or user.role is not None:
        return False
    user.role = role
    db.commit()
    return True


def admin_set_role(db: Session, user_id, role):
    if role not in ("student", "instructor"):
        return False
    user = db.get(User, user_id)
    if user is None or user.role == "admin":
        return False
    user.role = role
    db.commit()
    return True


def set_active(db: Session, user_id, active):
    user = db.get(User, user_id)
    if user is None or user.role == "admin":
        return False
    user.is_active = bool(active)
    db.commit()
    return True


def list_users(db: Session):
    from app.services.common import row_to_dict
    users = db.execute(select(User).order_by(User.created_at.desc(), User.id.desc())).scalars()
    return [row_to_dict(u) for u in users]


def count_role(db: Session, role):
    return db.execute(select(func.count()).select_from(User)
                      .where(User.role == role, User.is_active.is_(True))).scalar_one()
