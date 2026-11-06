"""Backup and restore of the SQLite database and the uploaded media files.

Pure Python (standard library only) so it can be used and tested without Django:
the database is copied with SQLite's online backup API, which yields a consistent
snapshot even while the site is running.
"""
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path


def create_backup(db_path, media_root, dest_dir, now=None):
    """Write ``learnhub-backup-<timestamp>.tar.gz`` into ``dest_dir`` and return its path."""
    db_path, media_root, dest_dir = Path(db_path), Path(media_root), Path(dest_dir)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    archive = dest_dir / f"learnhub-backup-{stamp}.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "db.sqlite3"
        source = sqlite3.connect(str(db_path))
        target = sqlite3.connect(str(snapshot))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(snapshot, arcname="db.sqlite3")
            if media_root.exists():
                tar.add(media_root, arcname="media")
    return archive


def restore_backup(archive, db_path, media_root):
    """Replace the database and media folder with the contents of ``archive``.

    The caller must stop the web server first. Existing files are moved aside
    (``*.before-restore``) rather than deleted.
    """
    archive, db_path, media_root = Path(archive), Path(db_path), Path(media_root)
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():  # refuse path traversal / links
                target = (Path(tmp) / member.name).resolve()
                if not str(target).startswith(str(Path(tmp).resolve())) or member.issym() or member.islnk():
                    raise ValueError(f"Unsafe path in archive: {member.name}")
            tar.extractall(tmp)
        extracted_db = Path(tmp) / "db.sqlite3"
        if not extracted_db.exists():
            raise ValueError("The archive does not contain db.sqlite3")
        if db_path.exists():
            db_path.rename(db_path.with_name(db_path.name + ".before-restore"))
        shutil.copy2(extracted_db, db_path)
        if media_root.exists():
            media_root.rename(media_root.with_name(media_root.name + ".before-restore"))
        extracted_media = Path(tmp) / "media"
        if extracted_media.exists():
            shutil.copytree(extracted_media, media_root)
        else:
            media_root.mkdir(parents=True)
