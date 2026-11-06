from django.db import models
from django.utils import timezone

from core.files import connect_file_cleanup, material_upload_to


class LearningMaterial(models.Model):
    """DD Fig-19 LearningMaterial (title, file), owned by a Course (composition)."""

    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="materials")
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to=material_upload_to, max_length=255)
    original_name = models.CharField(max_length=150, blank=True)  # display / download name only
    created_at = models.DateTimeField(default=timezone.now)  # publication order (SRS 18.2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["course", "created_at"], name="material_course_idx")]

    def __str__(self):
        return self.title


connect_file_cleanup(LearningMaterial, "file")
