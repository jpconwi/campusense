"""Super-admin data export for moving a complete application snapshot to removable media."""

import hashlib
import io
import json
import os
import time
import zipfile
from datetime import date, datetime, time as datetime_time
from decimal import Decimal
from pathlib import Path

from sqlalchemy import MetaData, select, text

from app import config
from app.models import Concern, PhotoDraft, Report, User
from app.services import private_document_service, upload_service


PRIVATE_DOCUMENTS = (
    ("verification_document", "verification_document_storage_key", "verification_filename"),
    ("verification_cor_document", "verification_cor_storage_key", "verification_cor_filename"),
    ("verification_id_back_document", "verification_id_back_storage_key", "verification_id_back_filename"),
    ("face_image", "face_image_storage_key", "face_image_filename"),
    ("face_scan_pdf", "face_scan_pdf_storage_key", "face_scan_pdf_filename"),
)


def _file_tree_size(folder):
    total = 0
    if not folder.exists():
        return total
    for path in folder.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _safe_name(value):
    name = Path(str(value or "file")).name
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in name)[:180] or "file"


def _remote_media_refs(db):
    images = set()
    for model in (Report, Concern, PhotoDraft):
        for row in db.scalars(select(model)).all():
            for field in ("image_filename", "resolution_image_filename"):
                filename = getattr(row, field, None)
                if filename:
                    images.add(_safe_name(filename))
    documents = []
    for user in db.scalars(select(User)).all():
        for binary_field, storage_field, filename_field in PRIVATE_DOCUMENTS:
            key = getattr(user, storage_field, None)
            if key:
                documents.append((user.id, binary_field, key, getattr(user, filename_field, None)))
    return sorted(images), documents


def estimate_export(db):
    """Estimate conservative uncompressed archive capacity without downloading assets."""
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        database_bytes = int(db.execute(text("SELECT pg_database_size(current_database())")).scalar_one())
    elif bind.dialect.name == "sqlite":
        database_path = bind.url.database
        database_bytes = Path(database_path).stat().st_size if database_path and database_path != ":memory:" else 0
    else:
        database_bytes = 0

    images, documents = _remote_media_refs(db)
    local_upload_bytes = _file_tree_size(config.UPLOAD_DIR)
    local_report_bytes = _file_tree_size(config.REPORTS_DIR)
    remote_bytes = 0
    unknown_remote = 0
    if upload_service._cloudinary_enabled():
        local_names = {p.name for p in config.UPLOAD_DIR.rglob("*") if p.is_file()} if config.UPLOAD_DIR.exists() else set()
        for filename in images:
            if filename in local_names:
                continue
            size = upload_service.get_image_size(filename)
            if size is None:
                unknown_remote += 1
            else:
                remote_bytes += size
    else:
        # Storage keys prove these files live in remote storage; without credentials
        # we cannot inspect their sizes or retrieve them for the archive.
        local_names = {p.name for p in config.UPLOAD_DIR.rglob("*") if p.is_file()} if config.UPLOAD_DIR.exists() else set()
        unknown_remote = sum(1 for filename in images if filename not in local_names) + len(documents)
        for _user_id, _field, key, _filename in documents:
            size = private_document_service.document_size(key)
            if size is None:
                unknown_remote += 1
            else:
                remote_bytes += size

    # JSONL metadata can be larger than the database's row pages. A 50% margin is
    # deliberately conservative; media files are added at their original byte size.
    estimate = int(database_bytes * 1.5 + local_upload_bytes + local_report_bytes + remote_bytes + 1024 * 1024)
    return {
        "estimated_bytes": estimate,
        "database_bytes": database_bytes,
        "local_upload_bytes": local_upload_bytes,
        "generated_report_bytes": local_report_bytes,
        "remote_attachment_bytes": remote_bytes,
        "unknown_remote_files": unknown_remote,
        "estimate_is_conservative": True,
        "estimate_complete": unknown_remote == 0,
        "archive_format": "ZIP",
        "estimated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _json_value(value):
    if isinstance(value, (datetime, date, datetime_time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, memoryview):
        return bytes(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _write_database(archive, db):
    metadata = MetaData()
    metadata.reflect(bind=db.get_bind())
    for table in metadata.sorted_tables:
        if table.name.startswith("sqlite_"):
            continue
        member = f"database/{_safe_name(table.name)}.jsonl"
        with archive.open(member, "w") as raw_stream:
            with io.TextIOWrapper(raw_stream, encoding="utf-8", write_through=True) as stream:
                result = db.execute(select(table).execution_options(stream_results=True)).mappings().yield_per(250)
                primary_keys = [column.name for column in table.primary_key.columns]
                for row in result:
                    row_key_values = [row.get(name) for name in primary_keys] if primary_keys else [time.time_ns()]
                    key_data = json.dumps(row_key_values, default=str, ensure_ascii=False).encode("utf-8")
                    row_key = hashlib.sha256(key_data).hexdigest()[:20]
                    record = {}
                    for column in table.columns:
                        value = row[column.name]
                        binary = _json_value(value)
                        if isinstance(binary, bytes):
                            if binary:
                                blob_path = f"database_blobs/{_safe_name(table.name)}/{row_key}/{_safe_name(column.name)}.bin"
                                archive.writestr(blob_path, binary)
                                record[column.name] = {"binary_file": blob_path, "size_bytes": len(binary)}
                            else:
                                record[column.name] = None
                        else:
                            record[column.name] = binary
                    stream.write(json.dumps(record, ensure_ascii=False, default=str, separators=(",", ":")) + "\n")


def _write_local_tree(archive, folder, archive_prefix):
    if not folder.exists():
        return
    for path in folder.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(folder).as_posix()
        archive.write(path, f"{archive_prefix}/{relative}")


def _write_cloudinary_media(archive, db):
    images, documents = _remote_media_refs(db)
    local_names = {p.name for p in config.UPLOAD_DIR.rglob("*") if p.is_file()} if config.UPLOAD_DIR.exists() else set()
    image_count = 0
    document_count = 0
    for filename in images:
        if filename in local_names:
            continue
        data, _mime = upload_service.get_image(filename)
        if data is None:
            raise RuntimeError(f"Could not retrieve stored report image {filename}; export stopped to avoid an incomplete archive.")
        archive.writestr(f"uploads/cloudinary/{filename}", data)
        image_count += 1

    for user_id, field, key, filename in documents:
        data = private_document_service.read_document(key)
        if data is None:
            raise RuntimeError(f"Could not retrieve private user document {user_id}/{field}; export stopped to avoid an incomplete archive.")
        extension = Path(_safe_name(filename or "document.bin")).suffix or ".bin"
        archive.writestr(f"private_documents/users/{user_id}/{field}{extension}", data)
        document_count += 1
    return image_count, document_count


def build_export(db, destination):
    """Build a full ZIP backup containing every reflected table and available file."""
    with zipfile.ZipFile(destination, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        _write_database(archive, db)
        _write_local_tree(archive, config.UPLOAD_DIR, "uploads/local")
        _write_local_tree(archive, config.REPORTS_DIR, "generated_reports")
        image_count, document_count = _write_cloudinary_media(archive, db)
        manifest = {
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "format": "NEMSAI full data export v1",
            "database": "All reflected database tables as JSONL; database binary values are separate files under database_blobs/.",
            "files": "Local uploads, generated reports, Cloudinary report photos, and offloaded private registration documents.",
            "cloudinary_report_images_included": image_count,
            "cloudinary_private_documents_included": document_count,
            "sensitive_data": "Includes user records, private registration documents, chat history, reports, concerns, and administrative data. Store this archive securely.",
        }
        archive.writestr("README-export.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return Path(destination).stat().st_size
