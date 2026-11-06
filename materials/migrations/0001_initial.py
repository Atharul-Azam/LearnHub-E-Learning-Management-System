import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

import core.files


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("courses", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="LearningMaterial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("file", models.FileField(max_length=255, upload_to=core.files.material_upload_to)),
                ("original_name", models.CharField(blank=True, max_length=150)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="materials", to="courses.course"
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="learningmaterial",
            index=models.Index(fields=["course", "created_at"], name="material_course_idx"),
        ),
    ]
