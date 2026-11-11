"""Move registration evidence from Neon/Postgres into private Cloudinary storage.

Usage from backend/: python scripts/offload_registration_files.py
       python scripts/offload_registration_files.py --apply
       python scripts/offload_registration_files.py --purge

Default is a read-only inventory. --apply uploads missing objects and saves keys,
but retains database copies. Run --purge separately only after reviewing the
inventory and confirming the uploaded files are available.
"""

import argparse
import hashlib

from sqlalchemy import case, func, select
from sqlalchemy.orm import load_only

from app import config
from app.database import SessionLocal
from app.models import User
from app.services.private_document_service import delete_document, read_document, store_document

FILES = (
    ("verification_document", "verification_document_storage_key", "verification_filename", "verification_content_type"),
    ("verification_cor_document", "verification_cor_storage_key", "verification_cor_filename", "verification_cor_content_type"),
    ("verification_id_back_document", "verification_id_back_storage_key", "verification_id_back_filename", "verification_id_back_content_type"),
    ("face_image", "face_image_storage_key", "face_image_filename", "face_image_content_type"),
    ("face_scan_pdf", "face_scan_pdf_storage_key", "face_scan_pdf_filename", "application/pdf"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Upload missing files and save their private storage keys")
    mode.add_argument("--purge", action="store_true", help="Clear database bytes only where an offloaded key exists")
    args = parser.parse_args()
    if (args.apply or args.purge) and not all((config.CLOUDINARY_CLOUD_NAME, config.CLOUDINARY_API_KEY,
                                               config.CLOUDINARY_API_SECRET)):
        parser.error("Configure the Cloudinary credentials before applying or purging.")

    total_files = total_bytes = ready_to_purge = 0
    with SessionLocal() as db:
        if not args.apply and not args.purge:
            length = func.pg_column_size if db.bind.dialect.name == "postgresql" else func.length
            blobs = [getattr(User, item[0]) for item in FILES]
            keys = [getattr(User, item[1]) for item in FILES]
            totals = db.execute(select(
                sum((func.coalesce(length(blob), 0) for blob in blobs), 0),
                sum((case((key.is_not(None), 1), else_=0) for key in keys), 0),
            )).one()
            total_bytes = int(totals[0] or 0)
            total_files = int(db.scalar(select(sum((case((blob.is_not(None), 1), else_=0)
                                                    for blob in blobs), 0))) or 0)
            ready_to_purge = int(totals[1] or 0)
            print(f"Registration files found: {total_files}")
            print(f"Database file bytes found (approximate): {total_bytes}")
            print(f"Files with offloaded keys: {ready_to_purge}")
            print("Dry run only. Use --apply to upload and verify private copies; use --purge later to clear verified database bytes.")
            return

        for user_id in db.scalars(select(User.id).order_by(User.id)).all():
            user = db.scalar(select(User).options(load_only(
                User.id, *(getattr(User, name) for pair in FILES for name in pair[:2]),
                *(getattr(User, pair[2]) for pair in FILES),
                *(getattr(User, pair[3]) for pair in FILES if isinstance(pair[3], str) and hasattr(User, pair[3]))
            )).where(User.id == user_id))
            changed = False
            for binary_col, key_col, filename_col, type_col in FILES:
                data = getattr(user, binary_col)
                key = getattr(user, key_col)
                if data:
                    total_files += 1
                    total_bytes += len(data)
                    if args.apply and not key:
                        filename = getattr(user, filename_col) or "document.bin"
                        content_type = type_col if type_col == "application/pdf" else getattr(user, type_col)
                        new_key = store_document(data, filename, content_type)
                        uploaded = read_document(new_key) if new_key else None
                        if uploaded is None or hashlib.sha256(uploaded).digest() != hashlib.sha256(data).digest():
                            if new_key:
                                delete_document(new_key)
                            raise RuntimeError(f"Verification failed for user {user.id}, file {binary_col}; database copy retained.")
                        setattr(user, key_col, new_key)
                        db.commit()
                        key, changed = new_key, False
                if key and data:
                    ready_to_purge += 1
                    if args.purge:
                        remote = read_document(key)
                        if remote is None or hashlib.sha256(remote).digest() != hashlib.sha256(data).digest():
                            raise RuntimeError(f"Stored copy verification failed for user {user.id}, file {binary_col}; database copy retained.")
                        setattr(user, binary_col, None)
                        changed = True
            if changed:
                db.commit()
            db.expunge(user)
    print(f"Registration files found: {total_files}")
    print(f"Database file bytes found: {total_bytes}")
    print(f"Files with offloaded keys eligible for purge: {ready_to_purge}")
    if args.apply:
        print("Upload pass complete. Database copies were retained; review and back up before running --purge.")
    else:
        print("Database binary columns cleared where offloaded keys exist. PostgreSQL space may require planned vacuum/reclamation to return to the Neon quota.")


if __name__ == "__main__":
    main()
