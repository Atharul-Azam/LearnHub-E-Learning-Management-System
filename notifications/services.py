"""Creating and reading notifications."""
import hashlib
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Notification

logger = logging.getLogger("learnhub")

PREFERENCE_FIELD = {
    Notification.Category.COURSES: "notify_courses",
    Notification.Category.ASSIGNMENTS: "notify_assignments",
    Notification.Category.DISCUSSION: "notify_discussion",
}


def notify(recipient, category, message, url="", dedupe_key=""):
    """Create one notification unless the user switched that category off or it already exists.

    Never raises: a failing notification must not break the action that caused it.
    """
    if recipient is None or not getattr(recipient, "is_active", False):
        return None
    if not getattr(recipient, PREFERENCE_FIELD[category], True):
        return None
    try:
        with transaction.atomic():
            note, created = Notification.objects.get_or_create(
                recipient=recipient,
                dedupe_key=dedupe_key or hashlib.sha1(f"{category}:{message}:{url}".encode()).hexdigest(),
                defaults={"category": category, "message": message[:255], "url": url},
            )
    except IntegrityError:  # concurrent duplicate - the unique constraint won
        return None
    except Exception:
        logger.exception("Could not create a notification")
        return None
    return note if created else None


def notify_many(recipients, category, message, url="", dedupe_key=""):
    return [notify(r, category, message, url, dedupe_key) for r in recipients]


def unread_count(user):
    return Notification.objects.filter(recipient=user, read_at__isnull=True).count()


def mark_read(user, pk):
    """Mark one of ``user``'s own notifications read. Returns it, or None if it is not theirs."""
    note = Notification.objects.filter(recipient=user, pk=pk).first()
    if note and note.read_at is None:
        note.read_at = timezone.now()
        note.save(update_fields=["read_at"])
    return note


def mark_all_read(user):
    return Notification.objects.filter(recipient=user, read_at__isnull=True).update(read_at=timezone.now())


REMINDER_WINDOW = timedelta(hours=48)


def generate_deadline_reminders(student):
    """Create a reminder for each unsubmitted assignment due within 48 hours.

    There is no background scheduler: reminders are produced when the student opens the
    dashboard or the notification list, and the dedupe key (assignment + deadline) means
    each deadline reminds once.
    """
    from assignments.models import Assignment, Submission

    now = timezone.now()
    submitted = Submission.objects.filter(student=student).values_list("assignment_id", flat=True)
    due = (
        Assignment.objects.filter(
            course__enrollments__student=student,
            course__visibility="published",
            deadline__gt=now,
            deadline__lte=now + REMINDER_WINDOW,
        )
        .exclude(pk__in=submitted)
        .select_related("course")
        .distinct()
    )
    from django.urls import reverse

    for assignment in due:
        notify(
            student,
            Notification.Category.ASSIGNMENTS,
            f"Deadline soon: '{assignment.title}' in {assignment.course.title} is due {assignment.deadline:%d %b %Y, %H:%M}.",
            reverse("assignments:student_detail", args=[assignment.pk]),
            f"deadline:{assignment.pk}:{int(assignment.deadline.timestamp())}",
        )
