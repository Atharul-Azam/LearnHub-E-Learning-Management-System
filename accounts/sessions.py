"""Revoking a user's server-side sessions (password change, 'sign out everywhere', deletion)."""
from django.contrib.sessions.models import Session
from django.utils import timezone


def revoke_sessions(user, keep_key=None):
    """Delete every stored session that belongs to ``user`` except ``keep_key``."""
    removed = 0
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if keep_key and session.session_key == keep_key:
            continue
        if str(session.get_decoded().get("_auth_user_id")) == str(user.pk):
            session.delete()
            removed += 1
    return removed
