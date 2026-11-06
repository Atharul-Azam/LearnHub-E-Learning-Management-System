"""Helpers shared by the automated tests (not imported by application code)."""
import io
import shutil
import tempfile
import zipfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

PASSWORD = "Passw0rd123"


class MediaTestCase(TestCase):
    """TestCase whose uploaded files go to a throw-away MEDIA_ROOT."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_dir = tempfile.mkdtemp(prefix="learnhub-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_dir)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_dir, ignore_errors=True)
        super().tearDownClass()


def make_user(email, role="student", status=None, name=None, password=PASSWORD):
    from accounts.models import User

    return User.objects.create_user(
        email=email, name=name or email.split("@")[0].title(), password=password, role=role, status=status
    )


def make_admin(email="admin@example.com"):
    from accounts.models import User

    return User.objects.create_superuser(email=email, name="Admin", password=PASSWORD)


def make_teacher(email="teacher@example.com", approved=True, **kw):
    from accounts.models import User

    status = User.Status.ACTIVE if approved else User.Status.PENDING
    return make_user(email, role="teacher", status=status, **kw)


def make_student(email="student@example.com", **kw):
    return make_user(email, role="student", **kw)


def make_course(teacher, title="Intro to Python", category="Programming", visibility="published", description="A course."):
    from courses.models import Course

    return Course.objects.create(
        teacher=teacher, title=title, category=category, description=description, visibility=visibility
    )


def enroll(student, course):
    from courses.models import Enrollment

    return Enrollment.objects.create(student=student, course=course)


def make_material(course, title="Lecture 1", name="lecture.pdf"):
    from materials.models import LearningMaterial

    material = LearningMaterial(course=course, title=title, original_name=name)
    material.file.save("stored.pdf", pdf_file(name), save=False)
    material.save()
    return material


def make_assignment(course, title="Assignment 1", deadline=None, max_marks=10):
    from assignments.models import Assignment

    return Assignment.objects.create(
        course=course,
        title=title,
        instructions="Do the work.",
        deadline=deadline or timezone.now() + timedelta(days=7),
        max_marks=max_marks,
    )


def make_submission(assignment, student, late=False):
    from assignments.models import Submission

    submission = Submission(assignment=assignment, student=student, is_late=late, original_name="work.pdf")
    submission.file.save("work.pdf", pdf_file("work.pdf"), save=False)
    submission.save()
    return submission


# ---- real (valid) file payloads ---------------------------------------------
def pdf_file(name="file.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n", content_type="application/pdf")


def png_file(name="thumb.png", size=(8, 8)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (79, 70, 229)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def docx_file(name="work.docx"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    return SimpleUploadedFile(name, buffer.getvalue())


def txt_file(name="notes.txt", text="hello world"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/plain")


def fake_file(name, content=b"MZ\x90\x00 not what the extension says"):
    """A file whose real content does not match its extension."""
    return SimpleUploadedFile(name, content)
