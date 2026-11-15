"""Private courses: invitation tokens, access requests, approval, revocation.

Security model
* A private course is never listed and its content is reachable only through an
  Enrollment (every content view already requires one).
* The invitation link carries a random, non-guessable token (256 bits). The link
  alone exposes only basic course information; it never grants access.
* A student must be logged in, ask for access, and the owning teacher approves.
  Approval creates the ordinary Enrollment, so progress, assignments, files and
  dashboards work unchanged. Revocation deletes that Enrollment.
* One request per student per course (database unique constraint).
"""
import logging
import secrets
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from core.services import BusinessRuleError
from notifications import services as notifications
from notifications.models import Notification

from .models import Course, CourseAccessRequest, Enrollment

logger = logging.getLogger("learnhub")
Status = CourseAccessRequest.Status

EXPIRY_CHOICES = {"never": None, "7": 7, "30": 30, "90": 90}


# ---- invitation link ---------------------------------------------------------
def generate_invite(course, expiry="never"):
    """Create (or replace) the invitation token. The previous link stops working at once."""
    if not course.is_private:
        raise BusinessRuleError("Invitation links are only used for private courses.")
    days = EXPIRY_CHOICES.get(expiry)
    course.invite_token = secrets.token_urlsafe(32)
    course.invite_expires_at = timezone.now() + timedelta(days=days) if days else None
    course.save(update_fields=["invite_token", "invite_expires_at", "updated_at"])
    return course.invite_token


def disable_invite(course):
    course.invite_token = None
    course.invite_expires_at = None
    course.save(update_fields=["invite_token", "invite_expires_at", "updated_at"])


def invite_url(course, request=None):
    if not course.invite_token:
        return ""
    path = reverse("courses:join", args=[course.invite_token])
    return request.build_absolute_uri(path) if request is not None else path


def sync_access(course):
    """Keep the token consistent with the access type (called after a course is saved)."""
    if course.is_private and not course.invite_token:
        generate_invite(course)
    elif not course.is_private and course.invite_token:
        disable_invite(course)


INVALID, EXPIRED = "invalid", "expired"


def resolve_invite(token):
    """Return (course, None) for a usable link, else (None, reason)."""
    if not token:
        return None, INVALID
    course = Course.objects.select_related("teacher").filter(invite_token=token).first()
    if course is None or not course.is_private or not course.is_published:
        return None, INVALID
    if course.invite_expires_at and course.invite_expires_at <= timezone.now():
        return None, EXPIRED
    return course, None


# ---- student side ------------------------------------------------------------
def request_access(student, course):
    """Create the access request. Returns the request; raises BusinessRuleError otherwise."""
    if Enrollment.objects.filter(student=student, course=course).exists():
        raise BusinessRuleError("You already have access to this course.")
    existing = CourseAccessRequest.objects.filter(student=student, course=course).first()
    if existing is not None:
        raise BusinessRuleError(_duplicate_message(existing))
    try:
        with transaction.atomic():
            access = CourseAccessRequest.objects.create(course=course, student=student)
    except IntegrityError:
        raise BusinessRuleError("You have already requested access to this course.")
    notifications.notify(
        course.teacher,
        Notification.Category.COURSES,
        f"{student.name} requested access to your private course '{course.title}'.",
        reverse("courses:teacher_requests", args=[course.pk]),
        f"access-request:{access.pk}",
    )
    return access


def _duplicate_message(access):
    return {
        Status.PENDING: "You have already requested access. Please wait for the teacher's decision.",
        Status.REJECTED: "Your access request for this course was rejected.",
        Status.REVOKED: "Your access to this course was revoked by the teacher.",
        Status.APPROVED: "You already have access to this course.",
    }[access.status]


# ---- teacher side ------------------------------------------------------------
def _owned_request(teacher, pk):
    access = (
        CourseAccessRequest.objects.select_for_update()
        .select_related("course", "student")
        .filter(pk=pk, course__teacher=teacher)
        .first()
    )
    if access is None:
        raise BusinessRuleError("That request was not found.")
    return access


@transaction.atomic
def approve_request(teacher, pk):
    access = _owned_request(teacher, pk)
    if access.status == Status.APPROVED:
        raise BusinessRuleError("This request is already approved.")
    access.status = Status.APPROVED
    access.decided_at = timezone.now()
    access.save(update_fields=["status", "decided_at"])
    Enrollment.objects.get_or_create(student=access.student, course=access.course)
    notifications.notify(
        access.student,
        Notification.Category.COURSES,
        f"Your request to join '{access.course.title}' was approved.",
        reverse("courses:open_course", args=[access.course_id]),
        f"access:{access.pk}:approved",
    )
    return access


@transaction.atomic
def reject_request(teacher, pk):
    access = _owned_request(teacher, pk)
    if access.status != Status.PENDING:
        raise BusinessRuleError("Only pending requests can be rejected.")
    access.status = Status.REJECTED
    access.decided_at = timezone.now()
    access.save(update_fields=["status", "decided_at"])
    notifications.notify(
        access.student,
        Notification.Category.COURSES,
        f"Your request to join '{access.course.title}' was not approved.",
        reverse("courses:browse"),
        f"access:{access.pk}:rejected",
    )
    return access


@transaction.atomic
def revoke_student(teacher, course, student):
    """Remove a student's access to one of the teacher's courses."""
    if course.teacher_id != teacher.pk:
        raise BusinessRuleError("You can only manage your own courses.")
    deleted, _ = Enrollment.objects.filter(course=course, student=student).delete()
    if not deleted:
        raise BusinessRuleError("That student is not enrolled in this course.")
    access, _ = CourseAccessRequest.objects.get_or_create(course=course, student=student)
    access.status = Status.REVOKED
    access.decided_at = timezone.now()
    access.save(update_fields=["status", "decided_at"])
    notifications.notify(
        student,
        Notification.Category.COURSES,
        f"Your access to '{course.title}' was removed by the teacher.",
        reverse("courses:browse"),
        f"access:{access.pk}:revoked:{int(access.decided_at.timestamp())}",
    )
