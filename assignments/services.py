"""Submission state machine (DD 6.3) and review workflow (UC12, UC16)."""
import logging

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from core.files import clean_display_name, schedule_file_delete
from core.services import BusinessRuleError
from notifications.models import Notification
from notifications.services import notify
from progress.services import sync_student_progress

from .models import Submission

logger = logging.getLogger("learnhub")


def submit_assignment(student, assignment, upload):
    """Create the student's submission for ``assignment``.

    Policy (docs/DECISIONS.md D-1): the documents define a single transition
    Not Submitted -> Submitted, with no replacement or resubmission, so a
    student has exactly one submission per assignment (also enforced by the
    ``unique_submission_per_student`` database constraint).

    The timestamp and lateness come from the server clock only:
    on time  <=>  submitted_at <= deadline.
    """
    if Submission.objects.filter(assignment=assignment, student=student).exists():
        raise BusinessRuleError("You have already submitted this assignment.")
    now = timezone.now()
    submission = Submission(
        assignment=assignment,
        student=student,
        original_name=clean_display_name(upload.name),
        submitted_at=now,
        is_late=now > assignment.deadline,
    )
    submission.file = upload
    try:
        with transaction.atomic():
            submission.save()  # the file is written to storage during save
            sync_student_progress(student, assignment.course)
    except IntegrityError as exc:
        if submission.file and submission.file.name:  # do not leave an orphan file
            schedule_file_delete(submission.file.storage, submission.file.name)
        raise BusinessRuleError("You have already submitted this assignment.") from exc
    except Exception:
        if submission.file and submission.file.name:
            schedule_file_delete(submission.file.storage, submission.file.name)
        raise
    notify(
        assignment.course.teacher,
        Notification.Category.ASSIGNMENTS,
        f"{student.name} submitted '{assignment.title}' in {assignment.course.title}.",
        reverse("assignments:teacher_detail", args=[assignment.pk]),
        f"submission:{submission.pk}",
    )
    return submission


def notify_new_assignment(assignment):
    """Tell every enrolled student about a new assignment (once per assignment)."""
    from courses.models import Enrollment

    url_ = reverse("assignments:student_detail", args=[assignment.pk])
    for enrollment in Enrollment.objects.filter(course=assignment.course).select_related("student"):
        notify(
            enrollment.student,
            Notification.Category.ASSIGNMENTS,
            f"New assignment '{assignment.title}' in {assignment.course.title}. Deadline {assignment.deadline:%d %b %Y, %H:%M}.",
            url_,
            f"assignment:{assignment.pk}",
        )


@transaction.atomic
def save_review(submission, marks, feedback):
    """Save marks + feedback and move the submission to Reviewed (DD 6.3).

    The caller validates 0 <= marks <= max_marks through ReviewForm; the range
    is checked again here so the rule cannot be bypassed. Saving again on an
    already Reviewed submission only updates the evaluation (docs/DECISIONS.md D-2).
    """
    submission = Submission.objects.select_for_update().select_related("assignment").get(pk=submission.pk)
    if marks < 0 or marks > submission.assignment.max_marks:
        raise BusinessRuleError(f"Marks must be between 0 and {submission.assignment.max_marks}.")
    submission.marks = marks
    submission.feedback = feedback
    submission.reviewed = True
    submission.reviewed_at = timezone.now()
    submission.save(update_fields=["marks", "feedback", "reviewed", "reviewed_at"])
    notify(
        submission.student,
        Notification.Category.ASSIGNMENTS,
        f"Marks published for '{submission.assignment.title}': {submission.marks}/{submission.assignment.max_marks}"
        + (" – the teacher left feedback." if feedback else "."),
        reverse("assignments:student_detail", args=[submission.assignment_id]),
        f"review:{submission.pk}",  # one notification per submission; later edits do not repeat it
    )
    return submission
