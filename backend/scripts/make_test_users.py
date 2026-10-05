"""
scripts/make_test_users.py - for the React smoke test only (frontend/tests/smoke.test.jsx).

Creates a student + an instructor in the database, sets the admin password
"long-enough-password" for the first ADMIN_EMAILS address, and writes signed
session cookies to a JSON file so the test can act as those users without Google.

    python -m scripts.make_test_users /tmp/cookies.json

Use a TEST database (DATABASE_URL=...campusense_test), never your real one.
"""

import base64
import json
import sys

from itsdangerous import TimestampSigner

from app import config
from app.database import SessionLocal, init_db
from app.services import admin_auth_service, user_service


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/cookies.json"
    secret = config.SECRET_KEY
    if not secret:
        sys.exit("SECRET_KEY must be set (the server signs the cookies with it).")
    admins = sorted(config.admin_emails())
    if not admins:
        sys.exit("ADMIN_EMAILS must be set.")
    init_db()

    def cookie(user_id):
        data = base64.b64encode(json.dumps({"user_id": user_id}).encode())
        return TimestampSigner(secret).sign(data).decode()

    with SessionLocal() as db:
        s = user_service.login_user(db, "g-sam", "Sam Student", "sam@nemsu.edu.ph", False)
        user_service.set_role_first_time(db, s.id, "student")
        i = user_service.login_user(db, "g-ines", "Ines Instructor", "ines@nemsu.edu.ph", False)
        user_service.set_role_first_time(db, i.id, "instructor")
        admin_auth_service.set_password(db, admins[0], "long-enough-password")
    with open(out, "w") as f:
        json.dump({"student": cookie(s.id), "instructor": cookie(i.id)}, f)
    print(f"Wrote {out}. Admin: {admins[0]} / long-enough-password")


if __name__ == "__main__":
    main()
