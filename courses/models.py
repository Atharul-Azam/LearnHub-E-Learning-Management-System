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

    class Meta:
        ordering = ["-enrolled_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["student", "course"], name="unique_enrollment"),
            models.CheckConstraint(condition=models.Q(progress__lte=100), name="enrollment_progress_max_100"),
        ]
        indexes = [models.Index(fields=["course", "enrolled_at"], name="enrollment_course_idx")]

    def __str__(self):
        return f"{self.student_id} -> {self.course_id}"


connect_file_cleanup(Course, "thumbnail")
