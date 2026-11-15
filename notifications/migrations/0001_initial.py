import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("courses", "Courses and access"),
                            ("assignments", "Assignments and marks"),
                            ("discussion", "Discussion and announcements"),
                        ],
                        max_length=12,
                    ),
                ),
                ("message", models.CharField(max_length=255)),
                ("url", models.CharField(blank=True, max_length=255)),
                ("dedupe_key", models.CharField(max_length=120)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(fields=("recipient", "dedupe_key"), name="unique_notification_event"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["recipient", "read_at", "created_at"], name="notif_recipient_idx"),
        ),
    ]
