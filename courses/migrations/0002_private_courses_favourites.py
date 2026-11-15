import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("courses", "0001_initial"),
    ]

    operations = [
        # Existing courses stay public (the default), so nothing changes for current data.
        migrations.AddField(
            model_name="course",
            name="access",
            field=models.CharField(choices=[("public", "Public"), ("private", "Private")], default="public", max_length=10),
        ),
        migrations.AddField(
            model_name="course",
            name="invite_token",
            field=models.CharField(blank=True, editable=False, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="course",
            name="invite_expires_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="enrollment",
            name="last_accessed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="CourseAccessRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("revoked", "Access revoked"),
                        ],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("requested_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                (
                    "course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="access_requests", to="courses.course"
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        limit_choices_to={"role": "student"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="course_access_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-requested_at", "-id"]},
        ),
        migrations.CreateModel(
            name="Favourite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="favourited_by", to="courses.course"
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        limit_choices_to={"role": "student"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favourites",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="courseaccessrequest",
            constraint=models.UniqueConstraint(fields=("course", "student"), name="unique_access_request"),
        ),
        migrations.AddIndex(
            model_name="courseaccessrequest",
            index=models.Index(fields=["course", "status"], name="access_req_course_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="favourite",
            constraint=models.UniqueConstraint(fields=("student", "course"), name="unique_favourite"),
        ),
    ]
