from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils import timezone

from core.files import connect_file_cleanup, thumbnail_upload_to


class Course(models.Model):
    """DD Fig-19 Course. 'Removed' (DD 6.4) is a permanent delete of the row."""

    class Visibility(models.TextChoices):
        PUBLISHED = "published", "Published"
        HIDDEN = "hidden", "Hidden"

    class Access(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,  # a teacher who owns courses cannot be deleted by accident
        related_name="courses",
        limit_choices_to={"role": "teacher"},
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=100)
    thumbnail = models.ImageField(upload_to=thumbnail_upload_to, blank=True)
    # DD 6.4: a newly created course is Published.
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PUBLISHED)
    # Public: listed for every student, anyone can enrol. Private: never listed; students
    # join through an invitation link plus teacher approval (courses/private.py).
    access = models.CharField(max_length=10, choices=Access.choices, default=Access.PUBLIC)
    invite_token = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    invite_expires_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["visibility", "category"], name="course_vis_cat_idx"),
            models.Index(fields=["teacher", "created_at"], name="course_teacher_idx"),
        ]

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        return self.visibility == self.Visibility.PUBLISHED

    @property
    def is_private(self):
        return self.access == self.Access.PRIVATE


class Enrollment(models.Model):
    """DD Fig-19 Enrollment (enrolledAt, progress). One row per student per course."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
        limit_choices_to={"role": "student"},
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    enrolled_at = models.DateTimeField(default=timezone.now)
    # Stored percentage, kept in sync by progress.services (see docs/DECISIONS.md D-3).
    progress = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    last_accessed_at = models.DateTimeField(null=True, blank=True)  # "recently viewed courses"

    class Meta:
        ordering = ["-enrolled_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["student", "course"], name="unique_enrollment"),
            models.CheckConstraint(condition=models.Q(progress__lte=100), name="enrollment_progress_max_100"),
        ]
        indexes = [models.Index(fields=["course", "enrolled_at"], name="enrollment_course_idx")]

    def __str__(self):
        return f"{self.student_id} -> {self.course_id}"


class CourseAccessRequest(models.Model):
    """A student's request to join a private course through its invitation link."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        REVOKED = "revoked", "Access revoked"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="access_requests")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_access_requests",
        limit_choices_to={"role": "student"},
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at", "-id"]
        constraints = [
            # One request per student per course: duplicate requests are impossible.
            models.UniqueConstraint(fields=["course", "student"], name="unique_access_request"),
        ]
        indexes = [models.Index(fields=["course", "status"], name="access_req_course_status_idx")]

    def __str__(self):
        return f"{self.student_id} -> {self.course_id} ({self.status})"


class Favourite(models.Model):
    """A course a student saved. One row per student per course."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favourites",
        limit_choices_to={"role": "student"},
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="favourited_by")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["student", "course"], name="unique_favourite")]

    def __str__(self):
        return f"{self.student_id} * {self.course_id}"


connect_file_cleanup(Course, "thumbnail")
