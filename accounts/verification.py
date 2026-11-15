"""E-mail verification: secure, time-limited, single-use links.

The token is produced by Django's PasswordResetTokenGenerator, whose hash covers
the user's primary key, e-mail address, verification flag, password hash and
last login. It is therefore

* non-guessable (HMAC with SECRET_KEY),
* time-limited (``settings.EMAIL_VERIFICATION_TIMEOUT`` seconds),
* single-use: once ``email_verified`` flips to True the hash changes and the
  same link stops working,
* tied to the e-mail address it was sent to.

Nothing about the token is stored in the database or written to the logs.
"""
import logging

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.cache import cache
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import User

logger = logging.getLogger("learnhub")


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "learnhub.accounts.EmailVerificationTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        login = "" if user.last_login is None else user.last_login.replace(microsecond=0, tzinfo=None)
        return f"{user.pk}{user.email}{int(user.email_verified)}{user.password}{login}{timestamp}"


token_generator = EmailVerificationTokenGenerator()


def build_verification_url(user, request=None):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = token_generator.make_token(user)
    path = reverse("accounts:verify_email", args=[uid, token])
    if request is not None:
        return request.build_absolute_uri(path)
    return f"{settings.SITE_URL.rstrip('/')}{path}"


def send_verification_email(user, request=None):
    """Send the verification message. Returns True if the mail backend accepted it."""
    url = build_verification_url(user, request)
    hours = max(1, settings.EMAIL_VERIFICATION_TIMEOUT // 3600)
    body = (
        f"Hello {user.name},\n\n"
        "Welcome to LearnHub. Please confirm your e-mail address by opening this link:\n\n"
        f"{url}\n\n"
        f"The link works once and expires in {hours} hour(s). "
        "If you did not create a LearnHub account, you can ignore this message.\n"
    )
    try:
        send_mail("Verify your LearnHub e-mail address", body, settings.DEFAULT_FROM_EMAIL, [user.email])
    except Exception:  # SMTP down / misconfigured: never crash registration
        logger.exception("Could not send verification e-mail to user %s", user.pk)
        return False
    return True


RESEND_COOLDOWN_SECONDS = 60


def resend_allowed(email):
    """At most one resend per address per minute (cache based, best effort)."""
    key = f"verify-resend:{email.lower()}"
    if cache.get(key):
        return False
    cache.set(key, 1, RESEND_COOLDOWN_SECONDS)
    return True


VERIFY_OK, VERIFY_ALREADY, VERIFY_INVALID = "ok", "already", "invalid"


def verify_email(uidb64, token):
    """Validate the link and mark the e-mail verified. Returns (result, user)."""
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return VERIFY_INVALID, None
    if user.email_verified:
        return VERIFY_ALREADY, user
    if not token_generator.check_token(user, token):
        return VERIFY_INVALID, user
    User.objects.filter(pk=user.pk, email_verified=False).update(email_verified=True)
    user.email_verified = True
    return VERIFY_OK, user
