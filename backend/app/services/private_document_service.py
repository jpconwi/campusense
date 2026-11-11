"""Private Cloudinary storage for registration evidence.

Keys contain only a random asset identifier, never student information. Assets use
Cloudinary's authenticated delivery type and are streamed through admin-only API routes.
"""

import mimetypes
import uuid

import httpx

from app.services.upload_service import _cloudinary, _cloudinary_enabled


def store_document(data, filename, content_type):
    """Upload bytes privately and return a storage key; None means use DB fallback."""
    if not data or not _cloudinary_enabled():
        return None
    extension = (filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else "bin")
    resource_type = "image" if (content_type or "").startswith("image/") else "raw"
    public_id = f"registration/{uuid.uuid4().hex}"
    if resource_type == "raw":
        public_id += f".{extension}"
    cloudinary = _cloudinary()
    cloudinary.uploader.upload(
        data, public_id=public_id, resource_type=resource_type,
        type="authenticated", overwrite=False, unique_filename=False,
    )
    return f"{resource_type}:{public_id}:{extension}"


def read_document(storage_key):
    """Fetch authenticated Cloudinary content server-side for an authorized route."""
    if not storage_key or not _cloudinary_enabled():
        return None
    resource_type, separator, details = storage_key.partition(":")
    if not separator or resource_type not in ("image", "raw"):
        return None
    public_id, format_separator, extension = details.rpartition(":")
    if not format_separator:  # compatibility with any earlier key format
        public_id = details
        extension = public_id.rsplit(".", 1)[-1] if resource_type == "raw" else "jpg"
    url = _cloudinary().utils.private_download_url(
        public_id, extension, resource_type=resource_type, type="authenticated")
    response = httpx.get(url, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.content


def content_type_for(filename, fallback="application/octet-stream"):
    return mimetypes.guess_type(filename or "")[0] or fallback


def delete_document(storage_key):
    if not storage_key or not _cloudinary_enabled():
        return
    resource_type, separator, details = storage_key.partition(":")
    public_id, format_separator, _extension = details.rpartition(":")
    if not format_separator:
        public_id = details
    if separator and resource_type in ("image", "raw"):
        _cloudinary().uploader.destroy(public_id, resource_type=resource_type,
                                       type="authenticated", invalidate=True)
