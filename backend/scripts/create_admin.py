"""
scripts/create_admin.py - set (or change) an admin password.

Run from the backend/ folder:   python -m scripts.create_admin
The email must already be listed in ADMIN_EMAILS (backend/.env).
The password is typed hidden and saved only as a salted Argon2 hash.
"""

import getpass
import sys

from app import config
from app.database import SessionLocal, init_db
from app.services import admin_auth_service
from app.services.common import ValidationError


def main():
    init_db()
    email = input("Admin email: ").strip().lower()
    password = getpass.getpass(f"New password (min {config.ADMIN_MIN_PASSWORD} characters): ")
    if password != getpass.getpass("Type it again: "):
        sys.exit("The two passwords do not match.")

    with SessionLocal() as db:
        try:
            admin_auth_service.set_password(db, email, password)
        except ValidationError as error:
            sys.exit(f"Not saved: {error}")

    print("Password saved.")
    print(f"Admin login address:  {config.PUBLIC_URL}{config.ADMIN_LOGIN_URL}")


if __name__ == "__main__":
    main()
