from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.management.backup import create_backup, restore_backup


class Command(BaseCommand):
    help = "Back up (default) or restore (--restore FILE) the SQLite database and uploaded media files."

    def add_arguments(self, parser):
        parser.add_argument("--dest", default=str(Path(settings.BASE_DIR) / "backups"), help="Folder for backup archives.")
        parser.add_argument("--restore", metavar="ARCHIVE", help="Restore from this archive (stop the web server first).")

    def handle(self, *args, **options):
        db_path = settings.DATABASES["default"]["NAME"]
        try:
            if options["restore"]:
                restore_backup(options["restore"], db_path, settings.MEDIA_ROOT)
                self.stdout.write(self.style.SUCCESS("Restore complete. Previous data kept as *.before-restore."))
            else:
                archive = create_backup(db_path, settings.MEDIA_ROOT, options["dest"])
                self.stdout.write(self.style.SUCCESS(f"Backup written to {archive}"))
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc))
