"""
services/upload_service.py - safe handling of optional image uploads.

* only PNG, JPG and WEBP images
* the real file content is checked, not just the file name
* the file is saved under a random name (the user's name is never used)
* the size limit is enforced while reading
"""

import uuid

from app import config
from app.services.common import ValidationError

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def _detect_type(header):
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return None


def save_image(upload):
    """`upload` is a FastAPI UploadFile (or None). Returns the saved file name, or None."""
    if upload is None or not getattr(upload, "filename", ""):
        return None

    extension = upload.filename.rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError("Only PNG, JPG or WEBP images are allowed.")

    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise ValidationError(f"The file is too large. The maximum is {config.MAX_UPLOAD_MB} MB.")

    real_type = _detect_type(data[:16])
    if real_type is None:
        raise ValidationError("That file is not a valid image.")

    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{real_type}"
    (config.UPLOAD_DIR / filename).write_bytes(data)
    return filename
