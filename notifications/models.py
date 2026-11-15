from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """An in-app notification. ``dedupe_key`` makes the same event notify a user only once."""

    class Category(models.TextChoices):
        COURSES = "courses", "Courses and access"
        ASSIGNMENTS = "assignments", "Assignments and marks"
        DISCUSSION = "discussion", "Discussion and announcements"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=12, choices=Category.choices)
    message = models.CharField(max_length=255)
    url = models.CharField(max_length=255, blank=True)  # internal path the notification leads to
    dedupe_key = models.CharField(max_length=120)
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["recipient", "dedupe_key"], name="unique_notification_event")]
        indexes = [models.Index(fields=["recipient", "read_at", "created_at"], name="notif_recipient_idx")]

    def __str__(self):
        return f"{self.recipient_id}: {self.message}"

    @property
    def is_read(self):
        return self.read_at is not None
