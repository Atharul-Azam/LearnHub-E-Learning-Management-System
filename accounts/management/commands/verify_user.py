"""Operator tool: mark an account's e-mail as verified without sending a message.

Use it when e-mail delivery is not available (for example a free host that blocks SMTP)
after you have confirmed the person's address by another way.

    python manage.py verify_user someone@example.com
"""
from django.core.management.base import BaseCommand, CommandError

from accounts.identifiers import ensure_public_id
from accounts.models import User


class Command(BaseCommand):
    help = "Mark the e-mail address of an account as verified."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        user = User.objects.filter(email__iexact=options["email"].strip()).first()
        if user is None:
            raise CommandError("No account with that e-mail address.")
        if user.email_verified:
            self.stdout.write("Already verified.")
            return
        user.email_verified = True
        user.save(update_fields=["email_verified"])
        if user.status == User.Status.ACTIVE:
            ensure_public_id(user)
        self.stdout.write(self.style.SUCCESS(f"{user.email} is now verified."))
