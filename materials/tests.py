import os

from django.test import override_settings
from django.urls import reverse

from core.factories import (
    MediaTestCase,
    docx_file,
    enroll,
    fake_file,
    make_admin,
    make_course,
    make_material,
    make_student,
    make_teacher,
    pdf_file,
    txt_file,
)
from progress.models import MaterialAccess

from .models import LearningMaterial


class MaterialUploadTests(MediaTestCase):  # UC9
    def setUp(self):
        self.teacher = make_teacher("t1@example.com")
        self.other = make_teacher("t2@example.com")
        self.course = make_course(self.teacher)
        self.client.force_login(self.teacher)
        self.url = reverse("materials:add", args=[self.course.pk])

    def test_upload_valid_pdf(self):
        response = self.client.post(self.url, {"title": "Lecture 1", "file": pdf_file("my lecture.pdf")})
        self.assertRedirects(response, reverse("courses:teacher_detail", args=[self.course.pk]))
        material = LearningMaterial.objects.get()
        self.assertEqual(material.course, self.course)
        self.assertEqual(material.title, "Lecture 1")
        self.assertEqual(material.original_name, "my lecture.pdf")
        self.assertTrue(material.file.name.startswith(f"materials/course_{self.course.pk}/"))
        self.assertNotIn("my lecture", material.file.name)
        self.assertTrue(os.path.exists(material.file.path))
        self.assertContains(self.client.get(reverse("courses:teacher_detail", args=[self.course.pk])), "Lecture 1")

    def test_other_accepted_types(self):
        for upload in (docx_file("a.docx"), txt_file("a.txt")):
            self.client.post(self.url, {"title": upload.name, "file": upload})
        self.assertEqual(LearningMaterial.objects.count(), 2)

    def test_title_and_file_are_required(self):
        self.assertEqual(self.client.post(self.url, {"title": "", "file": pdf_file()}).status_code, 200)
        self.assertEqual(self.client.post(self.url, {"title": "No file"}).status_code, 200)
        self.assertEqual(LearningMaterial.objects.count(), 0)

    def test_disallowed_types_are_rejected(self):
        for name in ("run.exe", "page.html", "script.php", "image.svg", "noextension"):
            response = self.client.post(self.url, {"title": "x", "file": fake_file(name)})
            self.assertEqual(response.status_code, 200, name)
            self.assertIn("file", response.context["form"].errors, name)
        self.assertEqual(LearningMaterial.objects.count(), 0)

    def test_content_must_match_extension(self):
        for name in ("fake.pdf", "fake.docx", "fake.zip", "fake.mp4"):
            response = self.client.post(self.url, {"title": "x", "file": fake_file(name)})
            self.assertContains(response, "does not match", msg_prefix=name)
        self.assertEqual(LearningMaterial.objects.count(), 0)

    def test_empty_file_rejected(self):
        response = self.client.post(self.url, {"title": "x", "file": fake_file("empty.pdf", b"")})
        self.assertEqual(LearningMaterial.objects.count(), 0)
        self.assertEqual(response.status_code, 200)

    def test_too_large_file_rejected(self):
        rules = {"material": {"extensions": {"pdf"}, "max_bytes": 20}}
        with override_settings(UPLOAD_RULES=rules):
            response = self.client.post(self.url, {"title": "x", "file": pdf_file()})
        self.assertContains(response, "too large")
        self.assertEqual(LearningMaterial.objects.count(), 0)

    def test_no_file_is_stored_for_a_rejected_upload(self):
        self.client.post(self.url, {"title": "x", "file": fake_file("fake.pdf")})
        folder = os.path.join(str(self.course.materials.model._meta.get_field("file").storage.location), "materials")
        self.assertFalse(os.path.isdir(folder) and any(files for _, _, files in os.walk(folder)))

    def test_other_teacher_cannot_upload_to_my_course(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {"title": "x", "file": pdf_file()}).status_code, 404)
        self.assertEqual(LearningMaterial.objects.count(), 0)

    def test_students_cannot_upload(self):
        self.client.force_login(make_student())
        self.assertEqual(self.client.post(self.url, {"title": "x", "file": pdf_file()}).status_code, 403)

    def test_replace_file_removes_old_file_and_keeps_publication_order(self):
        material = make_material(self.course, "Old")
        old_path, created = material.file.path, material.created_at
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("materials:edit", args=[material.pk]), {"title": "Renamed", "file": txt_file("new.txt")}
            )
        self.assertRedirects(response, reverse("courses:teacher_detail", args=[self.course.pk]))
        material.refresh_from_db()
        self.assertEqual((material.title, material.original_name), ("Renamed", "new.txt"))
        self.assertEqual(material.created_at, created)
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(material.file.path))

    def test_edit_title_only_keeps_file(self):
        material = make_material(self.course, "Old")
        path = material.file.path
        self.client.post(reverse("materials:edit", args=[material.pk]), {"title": "Only title"})
        material.refresh_from_db()
        self.assertEqual(material.title, "Only title")
        self.assertEqual(material.file.path, path)
        self.assertTrue(os.path.exists(path))

    def test_invalid_replacement_keeps_existing_material(self):
        material = make_material(self.course, "Keep")
        path = material.file.path
        response = self.client.post(reverse("materials:edit", args=[material.pk]), {"title": "Keep", "file": fake_file("x.pdf")})
        self.assertEqual(response.status_code, 200)
        material.refresh_from_db()
        self.assertEqual(material.file.path, path)
        self.assertTrue(os.path.exists(path))

    def test_remove_requires_confirmation_then_deletes_file(self):
        material = make_material(self.course)
        path = material.file.path
        url = reverse("materials:delete", args=[material.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(LearningMaterial.objects.exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url)
        self.assertFalse(LearningMaterial.objects.exists())
        self.assertFalse(os.path.exists(path))

    def test_other_teacher_cannot_edit_or_remove(self):
        material = make_material(self.course)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("materials:edit", args=[material.pk]), {"title": "Hack"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("materials:delete", args=[material.pk])).status_code, 404)
        self.assertTrue(LearningMaterial.objects.filter(pk=material.pk, title="Lecture 1").exists())

    def test_invalid_material_id(self):
        self.assertEqual(self.client.get(reverse("materials:edit", args=[99999])).status_code, 404)


class MaterialAccessTests(MediaTestCase):  # UC15
    def setUp(self):
        self.teacher = make_teacher()
        self.course = make_course(self.teacher)
        self.student = make_student("s@example.com")
        self.outsider = make_student("o@example.com")
        enroll(self.student, self.course)
        self.m1 = make_material(self.course, "First")
        self.m2 = make_material(self.course, "Second")

    def test_materials_listed_course_wise_in_publication_order(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("courses:open_course", args=[self.course.pk]))
        content = response.content.decode()
        self.assertLess(content.index("First"), content.index("Second"))
        self.assertEqual([m.title for m in response.context["materials"]], ["First", "Second"])

    def test_enrolled_student_can_view_and_download(self):
        self.client.force_login(self.student)
        view = self.client.get(reverse("materials:file", args=[self.m1.pk]))
        self.assertEqual(view.status_code, 200)
        self.assertEqual(view["Content-Type"], "application/pdf")
        self.assertIn("inline", view["Content-Disposition"])
        self.assertTrue(b"".join(view.streaming_content).startswith(b"%PDF"))
        download = self.client.get(reverse("materials:file", args=[self.m1.pk]), {"download": "1"})
        self.assertIn("attachment", download["Content-Disposition"])
        b"".join(download.streaming_content)

    def test_response_headers_are_safe(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("materials:file", args=[self.m1.pk]))
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", response["Cache-Control"])
        b"".join(response.streaming_content)

    def test_non_enrolled_student_is_denied(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("materials:file", args=[self.m1.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("courses:open_course", args=[self.course.pk])).status_code, 403)
        self.assertFalse(MaterialAccess.objects.exists())

    def test_anonymous_users_are_redirected_to_login(self):
        response = self.client.get(reverse("materials:file", args=[self.m1.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_media_is_not_publicly_routed(self):
        self.assertEqual(self.client.get("/media/" + self.m1.file.name).status_code, 404)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get("/media/" + self.m1.file.name).status_code, 404)

    def test_access_is_recorded_once_and_updates_progress(self):
        from courses.models import Enrollment

        self.client.force_login(self.student)
        for _ in range(3):
            b"".join(self.client.get(reverse("materials:file", args=[self.m1.pk])).streaming_content)
        self.assertEqual(MaterialAccess.objects.filter(student=self.student, material=self.m1).count(), 1)
        self.assertEqual(Enrollment.objects.get(student=self.student).progress, 50)  # 1 of 2 materials
        b"".join(self.client.get(reverse("materials:file", args=[self.m2.pk]), {"download": "1"}).streaming_content)
        self.assertEqual(Enrollment.objects.get(student=self.student).progress, 100)

    def test_owner_teacher_and_admin_can_open_without_recording(self):
        for user in (self.teacher, make_admin()):
            self.client.force_login(user)
            response = self.client.get(reverse("materials:file", args=[self.m1.pk]))
            self.assertEqual(response.status_code, 200)
            b"".join(response.streaming_content)
        self.assertFalse(MaterialAccess.objects.exists())

    def test_other_teacher_cannot_open(self):
        self.client.force_login(make_teacher("other@example.com"))
        self.assertEqual(self.client.get(reverse("materials:file", args=[self.m1.pk])).status_code, 404)

    def test_missing_file_on_disk_is_a_clean_404(self):
        os.remove(self.m1.file.path)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("materials:file", args=[self.m1.pk])).status_code, 404)

    def test_unknown_material(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("materials:file", args=[99999])).status_code, 404)

    def test_office_documents_are_always_downloaded(self):
        material = LearningMaterial(course=self.course, title="Doc", original_name="a.docx")
        material.file.save("x.docx", docx_file("a.docx"), save=False)
        material.save()
        self.client.force_login(self.student)
        response = self.client.get(reverse("materials:file", args=[material.pk]))
        self.assertIn("attachment", response["Content-Disposition"])
        b"".join(response.streaming_content)
