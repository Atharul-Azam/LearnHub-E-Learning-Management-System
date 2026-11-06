from django.conf import settings
from django.db import models
from django.utils import timezone


class MaterialAccess(models.Model):
    """Records that a student opened a learning material (UC15 post-condition 2).

    One row per student per material; it is the stored evidence from which the
    course progress percentage is derived (see progress/services.py).
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="material_accesses"
    )
    material = models.ForeignKey("materials.LearningMaterial", on_delete=models.CASCADE, related_name="accesses")
    first_accessed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "material"], name="unique_material_access")]
        indexes = [models.Index(fields=["student", "material"], name="access_student_material_idx")]

    def __str__(self):
        return f"{self.student_id} viewed {self.material_id}"
