from django.db import migrations, models

import core.files


def backfill(apps, schema_editor):
    """Existing accounts keep working: they count as verified and receive their ID.

    Students and teachers who have been approved (Active or Deactivated) get an
    ID in order of creation. Pending/Rejected teachers get one when approved.
    """
    User = apps.get_model("accounts", "User")
    User.objects.update(email_verified=True)
    counters = {"student": 0, "teacher": 0}
    prefixes = {"student": "STU", "teacher": "TCH"}
    queryset = User.objects.filter(role__in=["student", "teacher"]).order_by("date_joined", "id")
    for user in queryset:
        if user.role == "teacher" and user.status not in ("active", "deactivated"):
            continue
        counters[user.role] += 1
        User.objects.filter(pk=user.pk).update(public_id=f"{prefixes[user.role]}-{counters[user.role]:06d}")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.AddField(model_name="user", name="email_verified", field=models.BooleanField(default=False)),
        migrations.AddField(
            model_name="user",
            name="public_id",
            field=models.CharField(blank=True, editable=False, max_length=20, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="user",
            name="profile_picture",
            field=models.ImageField(blank=True, upload_to=core.files.avatar_upload_to),
        ),
        migrations.AddField(model_name="user", name="bio", field=models.TextField(blank=True, max_length=1000)),
        migrations.AddField(model_name="user", name="expertise", field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(
            model_name="user",
            name="theme",
            field=models.CharField(
                choices=[("system", "System default"), ("light", "Light"), ("dark", "Dark")],
                default="system",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="font",
            field=models.CharField(
                choices=[("sans", "Sans-serif (default)"), ("serif", "Serif"), ("mono", "Monospace")],
                default="sans",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="notify_courses",
            field=models.BooleanField(default=True, verbose_name="Course and access updates"),
        ),
        migrations.AddField(
            model_name="user",
            name="notify_assignments",
            field=models.BooleanField(default=True, verbose_name="Assignments, deadlines and marks"),
        ),
        migrations.AddField(
            model_name="user",
            name="notify_discussion",
            field=models.BooleanField(default=True, verbose_name="Discussion and announcements"),
        ),
        migrations.RunPython(backfill, noop),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=models.Q(("public_id__isnull", True))
                | models.Q(("public_id__startswith", "STU-"), ("role", "student"))
                | models.Q(("public_id__startswith", "TCH-"), ("role", "teacher")),
                name="user_public_id_matches_role",
            ),
        ),
    ]
