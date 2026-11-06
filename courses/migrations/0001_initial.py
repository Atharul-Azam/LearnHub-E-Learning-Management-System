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
    ]

    operations = [
        migrations.CreateModel(
            name="Course",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField()),
                ("category", models.CharField(max_length=100)),
                ("thumbnail", models.ImageField(blank=True, upload_to=core.files.thumbnail_upload_to)),
                (
                    "visibility",
                    models.CharField(
                        choices=[("published", "Published"), ("hidden", "Hidden")], default="published", max_length=10
                    ),
                ),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "teacher",
                    models.ForeignKey(
                        limit_choices_to={"role": "teacher"},
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="courses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="Enrollment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enrolled_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "progress",
                    models.PositiveSmallIntegerField(
                        default=0, validators=[django.core.validators.MaxValueValidator(100)]
                    ),
                ),
                (
                    "course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="enrollments", to="courses.course"
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        limit_choices_to={"role": "student"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="enrollments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-enrolled_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="course",
            index=models.Index(fields=["visibility", "category"], name="course_vis_cat_idx"),
        ),
        migrations.AddIndex(
            model_name="course",
            index=models.Index(fields=["teacher", "created_at"], name="course_teacher_idx"),
        ),
        migrations.AddIndex(
            model_name="enrollment",
            index=models.Index(fields=["course", "enrolled_at"], name="enrollment_course_idx"),
        ),
        migrations.AddConstraint(
            model_name="enrollment",
            constraint=models.UniqueConstraint(fields=("student", "course"), name="unique_enrollment"),
        ),
        migrations.AddConstraint(
            model_name="enrollment",
            constraint=models.CheckConstraint(condition=models.Q(("progress__lte", 100)), name="enrollment_progress_max_100"),
        ),
    ]
