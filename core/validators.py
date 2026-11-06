"""Server-side upload validation.

An upload is accepted only if ALL of these hold:
  1. its extension is on the configured allow-list for the upload kind,
  2. it is non-empty and not larger than the configured maximum,
  3. its real content (magic bytes / container structure) matches the extension.

The browser-supplied MIME type is deliberately ignored.
"""
import codecs
import os
import zipfile

from django.conf import settings
from django.core.exceptions import ValidationError

OLE_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
SNIFF_BYTES = 8192


def get_extension(name):
    return os.path.splitext(name or "")[1].lower().lstrip(".")


def _read_head(upload, size=SNIFF_BYTES):
    upload.seek(0)
    head = upload.read(size)
    upload.seek(0)
    return head


def _is_office_zip(upload, prefix):
    try:
        upload.seek(0)
        with zipfile.ZipFile(upload) as archive:
            names = archive.namelist()
    except Exception:  # BadZipFile, EOFError, OSError ...
        return False
    finally:
        upload.seek(0)
    return "[Content_Types].xml" in names and any(n.startswith(prefix) for n in names)


def _is_plain_text(head):
    if b"\x00" in head:
        return False
    try:
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
    except UnicodeDecodeError:
        return False
    return True


def content_matches_extension(upload, ext):
    """Return True when the file's actual bytes are consistent with ``ext``."""
    head = _read_head(upload)
    if ext == "pdf":
        return head.startswith(b"%PDF-")
    if ext == "png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in {"jpg", "jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    if ext == "gif":
        return head[:6] in (b"GIF87a", b"GIF89a")
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext == "docx":
        return _is_office_zip(upload, "word/")
    if ext == "pptx":
        return _is_office_zip(upload, "ppt/")
    if ext == "xlsx":
        return _is_office_zip(upload, "xl/")
    if ext in {"doc", "ppt", "xls"}:
        return head.startswith(OLE_HEADER)
    if ext == "zip":
        return head.startswith((b"PK\x03\x04", b"PK\x05\x06"))
    if ext == "mp4":
        return head[4:8] == b"ftyp"
    if ext == "txt":
        return _is_plain_text(head)
    return False


def validate_upload(upload, kind):
    """Validate ``upload`` against ``settings.UPLOAD_RULES[kind]``."""
    rule = settings.UPLOAD_RULES[kind]
    ext = get_extension(upload.name)
    allowed = sorted(rule["extensions"])
    if ext not in rule["extensions"]:
        raise ValidationError(
            "File type '.%(ext)s' is not accepted. Allowed types: %(allowed)s.",
            code="invalid_extension",
            params={"ext": ext or "unknown", "allowed": ", ".join(allowed)},
        )
    if upload.size == 0:
        raise ValidationError("The uploaded file is empty.", code="empty_file")
    if upload.size > rule["max_bytes"]:
        raise ValidationError(
            "The file is too large. The maximum size is %(limit)s MB.",
            code="file_too_large",
            params={"limit": rule["max_bytes"] // (1024 * 1024)},
        )
    if not content_matches_extension(upload, ext):
        raise ValidationError(
            "The content of the file does not match its '.%(ext)s' type.",
            code="content_mismatch",
            params={"ext": ext},
        )


def validate_thumbnail(upload):
    validate_upload(upload, "thumbnail")
    # Defence in depth: let Pillow parse the image completely.
    from PIL import Image

    ext = get_extension(upload.name)
    expected = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "gif": "GIF", "webp": "WEBP"}[ext]
    try:
        upload.seek(0)
        with Image.open(upload) as image:
            image.verify()
            actual = image.format
    except Exception as exc:
        raise ValidationError("The thumbnail is not a valid image.", code="invalid_image") from exc
    finally:
        upload.seek(0)
    if actual != expected:
        raise ValidationError("The thumbnail content does not match its file type.", code="invalid_image")


def validate_material(upload):
    validate_upload(upload, "material")


def validate_attachment(upload):
    validate_upload(upload, "attachment")


def validate_submission(upload):
    validate_upload(upload, "submission")
