from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.files import attachment_upload_to, connect_file_cleanup, submission_upload_to


class Assignment(models.Model):
    """DD Fig-19 Assignment, owned by a Course (composition). Published on creation (UC10)."""

    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="assignments")
    title = models.CharField(max_length=200)
    instructions = models.TextField()
    deadline = models.DateTimeField()
    max_marks = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    attachment = models.FileField(upload_to=attachment_upload_to, blank=True, max_length=255)
    attachment_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["deadline", "id"]
        constraints = [models.CheckConstraint(condition=models.Q(max_marks__gte=1), name="assignment_max_marks_positive")]
        indexes = [models.Index(fields=["course", "deadline"], name="assignment_course_idx")]

    def __str__(self):
        return self.title

    @property
    def is_past_deadline(self):
        return timezone.now() > self.deadline


class Submission(models.Model):
    """DD Fig-19 Submission (file, submittedAt, isLate, marks, feedback, reviewed).

    A row exists only after a valid upload, so "Not Submitted" is the absence of
    a row. The documented state of a row is derived by ``status``.
    """

    NOT_SUBMITTED = "not_submitted"
    ON_TIME = "submitted_on_time"
    LATE = "submitted_late"
    REVIEWED = "reviewed"
    STATUS_LABELS = {
        NOT_SUBMITTED: "Not Submitted",
        ON_TIME: "Submitted On Time",
        LATE: "Submitted Late",
        REVIEWED: "Reviewed",
    }

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions")
    file = models.FileField(upload_to=submission_upload_to, max_length=255)
    original_name = models.CharField(max_length=150, blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)  # always set server-side
    is_late = models.BooleanField(default=False)
    marks = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    reviewed = models.BooleanField(default=False)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["submitted_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["assignment", "student"], name="unique_submission_per_student"),
            models.CheckConstraint(
                condition=models.Q(marks__isnull=True) | models.Q(marks__gte=0), name="submission_marks_non_negative"
            ),
            # A reviewed submission must carry marks (DD 6.3: Reviewed only after valid marks are saved).
            models.CheckConstraint(
                condition=models.Q(reviewed=False) | models.Q(marks__isnull=False), name="submission_reviewed_has_marks"
            ),
        ]
        indexes = [
            models.Index(fields=["assignment", "submitted_at"], name="submission_assign_idx"),
            models.Index(fields=["student", "assignment"], name="submission_student_idx"),
        ]

    def __str__(self):
        return f"{self.student_id} / {self.assignment_id}"

    @property
    def status(self):
        if self.reviewed:
            return self.REVIEWED
        return self.LATE if self.is_late else self.ON_TIME

    @property
    def status_label(self):
        return self.STATUS_LABELS[self.status]


connect_file_cleanup(Assignment, "attachment")
connect_file_cleanup(Submission, "file")
