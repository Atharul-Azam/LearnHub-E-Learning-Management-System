"""Safe storage paths, permission-checked file serving and orphan clean-up."""
import logging
import mimetypes
import os
import re
import uuid

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete
from django.http import FileResponse, Http404

from .validators import get_extension

logger = logging.getLogger("learnhub")


# --------------------------------------------------------------------------
# upload_to callables (referenced by migrations - do not rename)
# Server-generated names: the client-supplied filename never reaches the disk,
# so path traversal and executable-extension tricks are impossible.
# --------------------------------------------------------------------------
def _stored_name(folder, filename):
    ext = get_extension(filename)
    suffix = f".{ext}" if ext else ""
    return f"{folder}/{uuid.uuid4().hex}{suffix}"


def thumbnail_upload_to(instance, filename):
    return _stored_name("thumbnails", filename)


def material_upload_to(instance, filename):
    return _stored_name(f"materials/course_{instance.course_id}", filename)


def attachment_upload_to(instance, filename):
    return _stored_name(f"attachments/course_{instance.course_id}", filename)


def submission_upload_to(instance, filename):
    return _stored_name(f"submissions/assignment_{instance.assignment_id}", filename)


def clean_display_name(name, limit=150):
    """Return a harmless version of the client's filename for display/download."""
    base = os.path.basename((name or "").replace("\\", "/"))
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    if len(base) > limit:
        stem, ext = os.path.splitext(base)
        base = stem[: limit - len(ext)] + ext
    return base or "file"


# --------------------------------------------------------------------------
# Serving
# --------------------------------------------------------------------------
def file_response(fieldfile, display_name, force_download=False):
    """Stream a stored file. Only reached after the caller's permission check."""
    if not fieldfile or not fieldfile.name:
        raise Http404("File not found.")
    try:
        handle = fieldfile.storage.open(fieldfile.name, "rb")
    except (FileNotFoundError, OSError) as exc:
        logger.error("Stored file missing: %s", fieldfile.name)
        raise Http404("File not found.") from exc
    display_name = clean_display_name(display_name or os.path.basename(fieldfile.name))
    ext = get_extension(display_name)
    inline_ok = ext in settings.INLINE_EXTENSIONS and not force_download
    content_type = mimetypes.guess_type(display_name)[0] or "application/octet-stream"
    response = FileResponse(
        handle,
        as_attachment=not inline_ok,
        filename=display_name,
        content_type=content_type,
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


# --------------------------------------------------------------------------
# Orphan clean-up. File deletion happens only after the DB transaction commits,
# because the file system is not rolled back with the database.
# --------------------------------------------------------------------------
def _delete_stored_file(storage, name):
    try:
        storage.delete(name)
    except Exception:  # never break a request because of clean-up
        logger.exception("Could not delete stored file %s", name)


def schedule_file_delete(storage, name):
    if name:
        transaction.on_commit(lambda: _delete_stored_file(storage, name))


def connect_file_cleanup(model, *field_names):
    """Delete the files of a model instance after the instance is deleted."""

    def _cleanup(sender, instance, **kwargs):
        for field_name in field_names:
            fieldfile = getattr(instance, field_name)
            if fieldfile and fieldfile.name:
                schedule_file_delete(fieldfile.storage, fieldfile.name)

    post_delete.connect(_cleanup, sender=model, weak=False, dispatch_uid=f"cleanup-{model.__name__}")
