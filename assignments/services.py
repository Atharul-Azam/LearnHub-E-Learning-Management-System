"""Submission state machine (DD 6.3) and review workflow (UC12, UC16)."""
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.files import clean_display_name, schedule_file_delete
from core.services import BusinessRuleError
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
    return submission


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
    return submission
