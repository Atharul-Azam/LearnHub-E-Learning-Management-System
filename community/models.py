from django.conf import settings
from django.db import models
from django.utils import timezone


class Announcement(models.Model):
    """A teacher's announcement to the students of one course."""

    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="announcements")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="announcements")
    title = models.CharField(max_length=150)
    body = models.TextField(max_length=3000)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title


class Post(models.Model):
    """A discussion question (parent is NULL) or a reply to one."""

    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="posts")
    # SET_NULL: when a student deletes their account the conversation stays for the others.
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="posts")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies")
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(default=timezone.now)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["course", "parent", "created_at"], name="post_course_thread_idx")]

    def __str__(self):
        return f"Post {self.pk} in course {self.course_id}"

    @property
    def is_question(self):
        return self.parent_id is None
