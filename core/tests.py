"""Validators, CSRF, direct-URL authorization and error handling (SRS 21-22)."""
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.factories import (
    PASSWORD,
    MediaTestCase,
    docx_file,
    enroll,
    fake_file,
    make_admin,
    make_assignment,
    make_course,
    make_material,
    make_student,
    make_submission,
    make_teacher,
    pdf_file,
    png_file,
    txt_file,
)
from core.files import clean_display_name, material_upload_to
from core.validators import validate_thumbnail, validate_upload


class FileValidatorTests(SimpleTestCase):
    def ok(self, upload, kind):
        validate_upload(upload, kind)

    def bad(self, upload, kind, code):
        with self.assertRaises(ValidationError) as ctx:
            validate_upload(upload, kind)
        self.assertEqual(ctx.exception.code, code)

    def test_valid_files(self):
        self.ok(pdf_file(), "material")
        self.ok(docx_file(), "submission")
        self.ok(txt_file(), "attachment")
        self.ok(png_file("a.png"), "submission")
        validate_thumbnail(png_file())

    def test_extension_allow_list(self):
        for name in ("a.exe", "a.sh", "a.php", "a.html", "a.svg", "a.js", "a.pdf.exe", "a"):
            self.bad(fake_file(name, b"%PDF-1.4 x"), "material", "invalid_extension")

    def test_extension_check_is_case_insensitive(self):
        self.ok(SimpleUploadedFile("A.PDF", pdf_file().read()), "material")

    def test_content_must_match_extension(self):
        self.bad(fake_file("a.pdf", b"MZ binary"), "material", "content_mismatch")
        self.bad(fake_file("a.png", b"%PDF-1.4 x"), "submission", "content_mismatch")
        self.bad(fake_file("a.docx", b"PK\x03\x04 but not office"), "submission", "content_mismatch")
        self.bad(fake_file("a.txt", b"abc\x00def"), "submission", "content_mismatch")
        self.bad(fake_file("a.txt", b"\xff\xfe\xfa binary"), "submission", "content_mismatch")

    def test_empty_and_oversized(self):
        self.bad(fake_file("a.pdf", b""), "material", "empty_file")
        with override_settings(UPLOAD_RULES={"material": {"extensions": {"pdf"}, "max_bytes": 5}}):
            self.bad(pdf_file(), "material", "file_too_large")

    def test_size_limit_boundary(self):
        size = len(pdf_file().read())
        with override_settings(UPLOAD_RULES={"material": {"extensions": {"pdf"}, "max_bytes": size}}):
            self.ok(pdf_file(), "material")
        with override_settings(UPLOAD_RULES={"material": {"extensions": {"pdf"}, "max_bytes": size - 1}}):
            self.bad(pdf_file(), "material", "file_too_large")

    def test_thumbnail_must_be_a_real_image(self):
        with self.assertRaises(ValidationError):
            validate_thumbnail(SimpleUploadedFile("a.png", b"\x89PNG\r\n\x1a\n" + b"garbage"))
        with self.assertRaises(ValidationError):
            validate_thumbnail(SimpleUploadedFile("a.jpg", png_file().read()))  # PNG data, .jpg name

    def test_stored_name_never_contains_client_filename(self):
        class Dummy:
            course_id = 7

        name = material_upload_to(Dummy(), "../../etc/passwd.pdf")
        self.assertRegex(name, r"^materials/course_7/[0-9a-f]{32}\.pdf$")

    def test_display_name_is_sanitised(self):
        self.assertEqual(clean_display_name("../../etc/passwd"), "passwd")
        self.assertEqual(clean_display_name("C:\\dir\\file.pdf"), "file.pdf")
        self.assertEqual(clean_display_name("a\x00b\nc.pdf"), "abc.pdf")
        self.assertEqual(clean_display_name(""), "file")
        self.assertLessEqual(len(clean_display_name("x" * 400 + ".pdf")), 150)


class CsrfTests(TestCase):
    def test_post_without_token_is_rejected(self):
        student, teacher = make_student(), make_teacher()
        course = make_course(teacher)
        client = Client(enforce_csrf_checks=True)
        client.force_login(student)
        response = client.post(reverse("courses:enroll", args=[course.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "could not be verified", status_code=403)
        self.assertEqual(course.enrollments.count(), 0)

    def test_login_and_register_require_token(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("accounts:login"), {"email": "a@b.c", "password": PASSWORD}).status_code, 403)
        self.assertEqual(client.post(reverse("accounts:register"), {"email": "a@b.c"}).status_code, 403)

    def test_destructive_actions_require_token(self):
        admin, teacher = make_admin(), make_teacher()
        course = make_course(teacher)
        client = Client(enforce_csrf_checks=True)
        client.force_login(admin)
        self.assertEqual(client.post(reverse("courses:admin_remove", args=[course.pk])).status_code, 403)
        self.assertEqual(client.post(reverse("accounts:remove_user", args=[teacher.pk])).status_code, 403)
        self.assertTrue(course.__class__.objects.filter(pk=course.pk).exists())

    def test_forms_contain_token(self):
        self.assertContains(self.client.get(reverse("accounts:login")), "csrfmiddlewaretoken")
        self.assertContains(self.client.get(reverse("accounts:register")), "csrfmiddlewaretoken")

    def test_state_changing_actions_do_not_run_on_get(self):
        admin, teacher, student = make_admin(), make_teacher(), make_student()
        pending = make_teacher("pending@example.com", approved=False)
        course = make_course(teacher)
        self.client.force_login(admin)
        for name, obj in (
            ("accounts:approve_teacher", pending),
            ("accounts:reject_teacher", pending),
            ("accounts:deactivate_user", student),
            ("accounts:remove_user", student),
            ("courses:admin_hide", course),
            ("courses:admin_remove", course),
        ):
            self.assertEqual(self.client.get(reverse(name, args=[obj.pk])).status_code, 200, name)  # confirmation page
        pending.refresh_from_db()
        student.refresh_from_db()
        course.refresh_from_db()
        self.assertEqual((pending.status, student.status, course.visibility), ("pending", "active", "published"))


class DirectUrlAuthorizationTests(MediaTestCase):
    """Every protected URL, requested by every kind of visitor."""

    def setUp(self):
        self.admin = make_admin()
        self.teacher = make_teacher("owner@example.com")
        self.other_teacher = make_teacher("other@example.com")
        self.student = make_student("in@example.com")
        self.outsider = make_student("out@example.com")
        self.course = make_course(self.teacher)
        enroll(self.student, self.course)
        self.material = make_material(self.course)
        self.assignment = make_assignment(self.course)
        self.submission = make_submission(self.assignment, self.student)
        pending = make_teacher("pend@example.com", approved=False)
        c = self.course.pk
        # url -> roles that may open it (everyone else must not get 200)
        self.matrix = {
            reverse("dashboards:admin"): {"admin"},
            reverse("accounts:teacher_requests"): {"admin"},
            reverse("accounts:teacher_request_detail", args=[pending.pk]): {"admin"},
            reverse("accounts:user_list"): {"admin"},
            reverse("accounts:user_detail", args=[self.student.pk]): {"admin"},
            reverse("courses:admin_list"): {"admin"},
            reverse("courses:admin_detail", args=[c]): {"admin"},
            reverse("dashboards:teacher"): {"teacher", "other_teacher"},
            reverse("courses:teacher_list"): {"teacher", "other_teacher"},
            reverse("courses:teacher_create"): {"teacher", "other_teacher"},
            reverse("courses:teacher_detail", args=[c]): {"teacher"},
            reverse("courses:teacher_edit", args=[c]): {"teacher"},
            reverse("courses:teacher_students", args=[c]): {"teacher"},
            reverse("materials:add", args=[c]): {"teacher"},
            reverse("materials:edit", args=[self.material.pk]): {"teacher"},
            reverse("assignments:teacher_add", args=[c]): {"teacher"},
            reverse("assignments:teacher_detail", args=[self.assignment.pk]): {"teacher"},
            reverse("assignments:teacher_edit", args=[self.assignment.pk]): {"teacher"},
            reverse("assignments:review", args=[self.submission.pk]): {"teacher"},
            reverse("dashboards:student"): {"student", "outsider"},
            reverse("courses:browse"): {"student", "outsider"},
            reverse("courses:my_courses"): {"student", "outsider"},
            reverse("courses:detail", args=[c]): {"student", "outsider"},
            reverse("courses:open_course", args=[c]): {"student"},
            reverse("progress:course_progress", args=[c]): {"student"},
            reverse("assignments:student_detail", args=[self.assignment.pk]): {"student"},
            reverse("materials:file", args=[self.material.pk]): {"student", "teacher", "admin"},
            reverse("assignments:submission_file", args=[self.submission.pk]): {"student", "teacher"},
        }

    def test_matrix(self):
        visitors = {
            "admin": self.admin,
            "teacher": self.teacher,
            "other_teacher": self.other_teacher,
            "student": self.student,
            "outsider": self.outsider,
        }
        for url, allowed in self.matrix.items():
            anonymous = self.client.get(url)
            self.assertEqual(anonymous.status_code, 302, f"anonymous {url}")
            self.assertIn(reverse("accounts:login"), anonymous["Location"], url)
            for label, user in visitors.items():
                client = Client()
                client.force_login(user)
                response = client.get(url)
                if hasattr(response, "streaming_content"):
                    b"".join(response.streaming_content)
                if label in allowed:
                    self.assertEqual(response.status_code, 200, f"{label} should open {url}")
                else:
                    self.assertIn(response.status_code, (403, 404), f"{label} must NOT open {url} (got {response.status_code})")

    def test_invalid_ids_return_404_for_every_role(self):
        names = [
            "courses:teacher_detail", "courses:teacher_edit", "courses:teacher_delete", "courses:teacher_students",
            "courses:admin_detail", "courses:detail", "courses:open_course", "courses:thumbnail",
            "materials:edit", "materials:file", "assignments:teacher_detail", "assignments:student_detail",
            "assignments:attachment", "assignments:submission_file", "assignments:review",
            "accounts:user_detail", "accounts:teacher_request_detail", "progress:course_progress",
        ]
        for user in (self.admin, self.teacher, self.student):
            self.client.force_login(user)
            for name in names:
                status = self.client.get(reverse(name, args=[987654])).status_code
                self.assertIn(status, (403, 404), f"{user.role} {name} -> {status}")
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("courses:teacher_detail", args=[987654])).status_code, 404)

    def test_non_numeric_ids_do_not_match_any_route(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/manage/courses/abc/").status_code, 404)
        self.assertEqual(self.client.get("/files/materials/1;DROP/").status_code, 404)

    def test_path_traversal_in_urls_is_not_possible(self):
        self.client.force_login(self.student)
        for path in ("/files/materials/../../etc/passwd", "/files/materials/%2e%2e/%2e%2e/etc/passwd", "/media/../db.sqlite3"):
            self.assertEqual(self.client.get(path).status_code, 404, path)


class ErrorHandlingTests(TestCase):
    def test_404_page_is_friendly_and_leaks_nothing(self):
        response = self.client.get("/no/such/page/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)
        self.assertNotContains(response, "Traceback", status_code=404)

    def test_403_page(self):
        self.client.force_login(make_student())
        response = self.client.get(reverse("dashboards:admin"))
        self.assertContains(response, "Access denied", status_code=403)

    def test_500_template_is_standalone(self):
        from django.template.loader import render_to_string

        html = render_to_string("errors/500.html")
        self.assertIn("Something went wrong", html)
        self.assertNotIn("{%", html)

    def test_root_redirects(self):
        self.assertRedirects(self.client.get("/"), reverse("accounts:login"), fetch_redirect_response=False)
        self.client.force_login(make_student())
        self.assertRedirects(self.client.get("/"), reverse("dashboards:home"), fetch_redirect_response=False)


class SettingsTests(SimpleTestCase):
    def test_security_relevant_settings(self):
        from django.conf import settings

        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)
        self.assertIn("django.middleware.clickjacking.XFrameOptionsMiddleware", settings.MIDDLEWARE)
        self.assertEqual(settings.DATABASES["default"]["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")

    def test_upload_limits_are_configurable_rules(self):
        from django.conf import settings

        for kind in ("thumbnail", "material", "attachment", "submission"):
            self.assertGreater(settings.UPLOAD_RULES[kind]["max_bytes"], 0)
            self.assertTrue(settings.UPLOAD_RULES[kind]["extensions"])
        for risky in ("exe", "html", "svg", "php", "js", "sh", "bat"):
            for kind in settings.UPLOAD_RULES.values():
                self.assertNotIn(risky, kind["extensions"])


class BackupRestoreTests(SimpleTestCase):  # SRS 24.1, 24.5
    def test_backup_and_restore_round_trip(self):
        import shutil
        import sqlite3
        import tempfile
        from pathlib import Path

        from core.management.backup import create_backup, restore_backup

        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        db = root / "db.sqlite3"
        connection = sqlite3.connect(db)
        connection.execute("create table t(a)")
        connection.execute("insert into t values ('kept')")
        connection.commit()
        connection.close()
        media = root / "media"
        (media / "materials").mkdir(parents=True)
        (media / "materials" / "f.pdf").write_bytes(b"%PDF-1")
        archive = create_backup(db, media, root / "backups")
        self.assertTrue(archive.exists())
        db.unlink()
        shutil.rmtree(media)
        restore_backup(archive, db, media)
        self.assertEqual(sqlite3.connect(db).execute("select a from t").fetchall(), [("kept",)])
        self.assertEqual((media / "materials" / "f.pdf").read_bytes(), b"%PDF-1")

    def test_missing_database_is_reported(self):
        from core.management.backup import create_backup

        with self.assertRaises(FileNotFoundError):
            create_backup("/nonexistent/db.sqlite3", "/nonexistent/media", "/tmp/never-created-backups")
