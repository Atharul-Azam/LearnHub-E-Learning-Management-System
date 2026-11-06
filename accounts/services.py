"""Account business rules: the user-account state machine of DD section 6.1."""
import logging

from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

from core.services import BusinessRuleError

from .models import User

logger = logging.getLogger("learnhub")

S = User.Status

# (current status, new status) pairs allowed by the DD state machine.
ALLOWED_TRANSITIONS = {
    (S.PENDING, S.ACTIVE),  # approve()
    (S.PENDING, S.REJECTED),  # reject()
    (S.ACTIVE, S.DEACTIVATED),  # deactivate()
    (S.DEACTIVATED, S.ACTIVE),  # activate()
}

# Statuses from which remove() is allowed (DD Fig-37 has no remove() from Pending).
REMOVABLE_STATUSES = {S.ACTIVE, S.REJECTED, S.DEACTIVATED}


def managed_accounts():
    """Accounts the administrator manages in UC3/UC4 (students and teachers only)."""
    return User.objects.filter(role__in=[User.Role.STUDENT, User.Role.TEACHER])


@transaction.atomic
def change_status(user, new_status, decided_by):
    """Move ``user`` to ``new_status`` if the state machine allows it."""
    user = User.objects.select_for_update().get(pk=user.pk)
    if user.role == User.Role.ADMIN:
        raise BusinessRuleError("Administrator accounts cannot be changed here.")
    if (user.status, new_status) not in ALLOWED_TRANSITIONS:
        raise BusinessRuleError(
            f"A {user.get_status_display().lower()} account cannot be changed to "
            f"{User.Status(new_status).label.lower()}."
        )
    user.status = new_status
    user.decided_at = timezone.now()
    user.decided_by = decided_by
    user.save(update_fields=["status", "decided_at", "decided_by"])
    return user


def approve_teacher(user, admin):
    if user.role != User.Role.TEACHER:
        raise BusinessRuleError("Only teacher registrations can be approved.")
    return change_status(user, S.ACTIVE, admin)


def reject_teacher(user, admin):
    if user.role != User.Role.TEACHER:
        raise BusinessRuleError("Only teacher registrations can be rejected.")
    return change_status(user, S.REJECTED, admin)


def activate_account(user, admin):
    return change_status(user, S.ACTIVE, admin)


def deactivate_account(user, admin):
    return change_status(user, S.DEACTIVATED, admin)


@transaction.atomic
def remove_account(user):
    """Permanently delete an account (after the view has obtained confirmation).

    * Students: their enrollments, progress records and submissions are
      removed with them (their own records); uploaded files are cleaned up
      after commit by the post_delete handlers.
    * Teachers who still own courses cannot be removed - the administrator
      must first remove or reassign the courses (UC5). This avoids silently
      destroying other students' academic records.
    """
    user = User.objects.select_for_update().get(pk=user.pk)
    if user.role == User.Role.ADMIN:
        raise BusinessRuleError("Administrator accounts cannot be removed here.")
    if user.status not in REMOVABLE_STATUSES:
        raise BusinessRuleError(
            "A pending teacher request must be approved or rejected before the account can be removed."
        )
    if user.role == User.Role.TEACHER and user.courses.exists():
        raise BusinessRuleError(
            "This teacher still owns courses. Remove their courses first, then remove the account."
        )
    try:
        user.delete()
    except ProtectedError as exc:  # database-level guard
        raise BusinessRuleError("This account is still referenced by other records.") from exc
