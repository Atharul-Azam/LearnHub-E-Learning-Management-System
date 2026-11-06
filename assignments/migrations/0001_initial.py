import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import core.files


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("courses", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Assignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("instructions", models.TextField()),
                ("deadline", models.DateTimeField()),
                (
                    "max_marks",
                    models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)]),
                ),
                (
                    "attachment",
                    models.FileField(blank=True, max_length=255, upload_to=core.files.attachment_upload_to),
                ),
                ("attachment_name", models.CharField(blank=True, max_length=150)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="assignments", to="courses.course"
                    ),
                ),
            ],
            options={"ordering": ["deadline", "id"]},
        ),
        migrations.CreateModel(
            name="Submission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(max_length=255, upload_to=core.files.submission_upload_to)),
                ("original_name", models.CharField(blank=True, max_length=150)),
                ("submitted_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("is_late", models.BooleanField(default=False)),
                ("marks", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ("feedback", models.TextField(blank=True)),
                ("reviewed", models.BooleanField(default=False)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="submissions",
                        to="assignments.assignment",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["submitted_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="assignment",
            index=models.Index(fields=["course", "deadline"], name="assignment_course_idx"),
        ),
        migrations.AddConstraint(
            model_name="assignment",
            constraint=models.CheckConstraint(condition=models.Q(("max_marks__gte", 1)), name="assignment_max_marks_positive"),
        ),
        migrations.AddIndex(
            model_name="submission",
            index=models.Index(fields=["assignment", "submitted_at"], name="submission_assign_idx"),
        ),
        migrations.AddIndex(
            model_name="submission",
            index=models.Index(fields=["student", "assignment"], name="submission_student_idx"),
        ),
        migrations.AddConstraint(
            model_name="submission",
            constraint=models.UniqueConstraint(fields=("assignment", "student"), name="unique_submission_per_student"),
        ),
        migrations.AddConstraint(
            model_name="submission",
            constraint=models.CheckConstraint(
                condition=models.Q(("marks__isnull", True), ("marks__gte", 0), _connector="OR"),
                name="submission_marks_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="submission",
            constraint=models.CheckConstraint(
                condition=models.Q(("reviewed", False), ("marks__isnull", False), _connector="OR"),
                name="submission_reviewed_has_marks",
            ),
        ),
    ]
