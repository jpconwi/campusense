"""
services/upload_service.py - safe handling of optional image uploads.

* only PNG, JPG and WEBP images
* the real file content is checked, not just the file name
* the file is saved under a random name (the user's name is never used)
* the size limit is enforced while reading
"""

import mimetypes
import time
import uuid

import httpx

from app import config
from app.services.common import ValidationError

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def _cloudinary_enabled():
    return all((config.CLOUDINARY_CLOUD_NAME, config.CLOUDINARY_API_KEY,
                config.CLOUDINARY_API_SECRET))


def _cloudinary():
    import cloudinary
    cloudinary.config(cloud_name=config.CLOUDINARY_CLOUD_NAME,
                      api_key=config.CLOUDINARY_API_KEY,
                      api_secret=config.CLOUDINARY_API_SECRET,
                      secure=True)
    return cloudinary


def _public_id(filename):
    return filename.rsplit(".", 1)[0]


def _cloudinary_upload(path, filename):
    _cloudinary().uploader.upload(
        str(path), public_id=_public_id(filename), resource_type="image",
        type="authenticated", overwrite=False, unique_filename=False)


def _content_type(filename):
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


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
    local_path = config.UPLOAD_DIR / filename
    local_path.write_bytes(data)
    if _cloudinary_enabled():
        try:
            _cloudinary_upload(local_path, filename)
        except Exception as exc:
            local_path.unlink(missing_ok=True)
            print("REPORT PHOTO CLOUDINARY ERROR:", repr(exc)[:200])
            raise ValidationError("The photo couldn't be saved. Please try again.") from exc
    return filename


def get_image(filename):
    """Return image bytes and MIME type, preferring private Cloudinary storage."""
    if _cloudinary_enabled():
        try:
            cld = _cloudinary()
            url = cld.utils.private_download_url(
                _public_id(filename), filename.rsplit(".", 1)[-1],
                resource_type="image", type="authenticated",
                expires_at=int(time.time()) + 60)
            response = httpx.get(url, timeout=30, follow_redirects=True)
            response.raise_for_status()
            return response.content, _content_type(filename)
        except Exception as exc:
            # A deployment may have started before object storage was configured. Local
            # fallback keeps any still-present uploads accessible while new ones use Cloudinary.
            print("REPORT PHOTO CLOUDINARY READ ERROR:", repr(exc)[:200])
    path = config.UPLOAD_DIR / filename
    if path.is_file():
        data = path.read_bytes()
        if _cloudinary_enabled():
            try:
                _cloudinary_upload(path, filename)
            except Exception as exc:
                print("REPORT PHOTO CLOUDINARY MIGRATION ERROR:", repr(exc)[:200])
        return data, _content_type(filename)
    return None, None


def get_image_path(filename):
    """Get a local path for image analysis/PDF rendering, downloading from Cloudinary if needed."""
    path = config.UPLOAD_DIR / filename
    if path.is_file():
        return path
    data, _ = get_image(filename)
    if data is None:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def delete_image(filename):
    if not filename:
        return
    try:
        (config.UPLOAD_DIR / filename).unlink(missing_ok=True)
    except OSError:
        pass
    if _cloudinary_enabled():
        try:
            _cloudinary().uploader.destroy(
                _public_id(filename), resource_type="image", type="authenticated",
                invalidate=True)
        except Exception as exc:
            print("REPORT PHOTO CLOUDINARY DELETE ERROR:", repr(exc)[:200])
