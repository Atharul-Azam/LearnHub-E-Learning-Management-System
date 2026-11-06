import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("materials", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MaterialAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_accessed_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "material",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="accesses",
                        to="materials.learningmaterial",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="material_accesses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="materialaccess",
            index=models.Index(fields=["student", "material"], name="access_student_material_idx"),
        ),
        migrations.AddConstraint(
            model_name="materialaccess",
            constraint=models.UniqueConstraint(fields=("student", "material"), name="unique_material_access"),
        ),
    ]
