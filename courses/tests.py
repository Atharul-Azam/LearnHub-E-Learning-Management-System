import os

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from core.factories import (
    MediaTestCase,
    enroll,
    fake_file,
    make_admin,
    make_assignment,
    make_course,
    make_material,
    make_student,
    make_submission,
    make_teacher,
    png_file,
    txt_file,
)

from .models import Course, Enrollment
from . import services


class TeacherCourseTests(MediaTestCase):  # UC7, UC8
    def setUp(self):
        self.teacher = make_teacher("t1@example.com")
        self.other = make_teacher("t2@example.com")
        self.client.force_login(self.teacher)
        self.data = {"title": "  Data   Structures ", "description": "Lists, trees.", "category": "CS"}

    def test_create_course_defaults_to_published_and_owned(self):
        response = self.client.post(reverse("courses:teacher_create"), self.data)
        course = Course.objects.get()
        self.assertRedirects(response, reverse("courses:teacher_detail", args=[course.pk]))
        self.assertEqual(course.teacher, self.teacher)
        self.assertEqual(course.visibility, Course.Visibility.PUBLISHED)
        self.assertEqual(course.title, "Data Structures")
        self.assertFalse(course.thumbnail)

    def test_create_with_valid_thumbnail_and_random_server_filename(self):
        self.data["thumbnail"] = png_file("my thumb ../../x.png")
        self.client.post(reverse("courses:teacher_create"), self.data)
        course = Course.objects.get()
        self.assertTrue(course.thumbnail)
        self.assertTrue(course.thumbnail.name.startswith("thumbnails/"))
        self.assertNotIn("..", course.thumbnail.name)
        self.assertNotIn("my thumb", course.thumbnail.name)
        self.assertTrue(os.path.exists(course.thumbnail.path))

    def test_default_image_is_used_when_no_thumbnail(self):
        self.client.post(reverse("courses:teacher_create"), self.data)
        response = self.client.get(reverse("courses:teacher_list"))
        self.assertContains(response, "default_thumbnail.svg")

    def test_required_fields(self):
        for missing in ("title", "description", "category"):
            data = dict(self.data)
            data[missing] = "   "
            response = self.client.post(reverse("courses:teacher_create"), data)
            self.assertEqual(response.status_code, 200, missing)
            self.assertEqual(Course.objects.count(), 0, missing)
            self.assertTrue(response.context["form"].errors, missing)

    def test_invalid_thumbnails_are_rejected(self):
        bad = {
            "txt": txt_file("thumb.txt"),
            "extension": fake_file("thumb.png", b"this is not a png"),
            "exe": fake_file("thumb.exe"),
            "svg": fake_file("thumb.svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
        }
        for label, upload in bad.items():
            data = dict(self.data, thumbnail=upload)
            response = self.client.post(reverse("courses:teacher_create"), data)
            self.assertEqual(response.status_code, 200, label)
            self.assertIn("thumbnail", response.context["form"].errors, label)
        self.assertEqual(Course.objects.count(), 0)

    def test_thumbnail_too_large(self):
        rules = {"thumbnail": {"extensions": {"png"}, "max_bytes": 10}}
        with override_settings(UPLOAD_RULES=rules):
            response = self.client.post(reverse("courses:teacher_create"), dict(self.data, thumbnail=png_file()))
        self.assertContains(response, "too large")
        self.assertEqual(Course.objects.count(), 0)

    def test_edit_own_course(self):
        course = make_course(self.teacher)
        response = self.client.post(
            reverse("courses:teacher_edit", args=[course.pk]),
            {"title": "New title", "description": "New", "category": "Math"},
        )
        self.assertRedirects(response, reverse("courses:teacher_detail", args=[course.pk]))
        course.refresh_from_db()
        self.assertEqual((course.title, course.category), ("New title", "Math"))

    def test_edit_invalid_does_not_change_course(self):
        course = make_course(self.teacher)
        self.client.post(reverse("courses:teacher_edit", args=[course.pk]), {"title": "", "description": "x", "category": "y"})
        course.refresh_from_db()
        self.assertEqual(course.title, "Intro to Python")

    def test_replacing_and_removing_thumbnail_deletes_old_file(self):
        self.client.post(reverse("courses:teacher_create"), dict(self.data, thumbnail=png_file()))
        course = Course.objects.get()
        first = course.thumbnail.path
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("courses:teacher_edit", args=[course.pk]), dict(self.data, thumbnail=png_file("b.png"))
            )
        course.refresh_from_db()
        self.assertFalse(os.path.exists(first))
        second = course.thumbnail.path
        self.assertTrue(os.path.exists(second))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("courses:teacher_edit", args=[course.pk]), dict(self.data, remove_thumbnail="on"))
        course.refresh_from_db()
        self.assertFalse(course.thumbnail)
        self.assertFalse(os.path.exists(second))

    def test_cannot_edit_or_delete_another_teachers_course(self):
        course = make_course(self.other)
        for name in ("courses:teacher_edit", "courses:teacher_delete", "courses:teacher_detail", "courses:teacher_students"):
            self.assertEqual(self.client.get(reverse(name, args=[course.pk])).status_code, 404, name)
        self.assertEqual(
            self.client.post(reverse("courses:teacher_edit", args=[course.pk]), {"title": "Hacked", "description": "x", "category": "y"}).status_code,
            404,
        )
        self.assertEqual(self.client.post(reverse("courses:teacher_delete", args=[course.pk])).status_code, 404)
        course.refresh_from_db()
        self.assertEqual(course.title, "Intro to Python")

    def test_delete_requires_confirmation_and_cascades(self):
        course = make_course(self.teacher)
        student = make_student()
        enroll(student, course)
        material = make_material(course)
        assignment = make_assignment(course)
        submission = make_submission(assignment, student)
        file_paths = [material.file.path, submission.file.path]
        url = reverse("courses:teacher_delete", args=[course.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(Course.objects.filter(pk=course.pk).exists())
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url)
        self.assertRedirects(response, reverse("courses:teacher_list"))
        self.assertFalse(Course.objects.filter(pk=course.pk).exists())
        self.assertEqual(Enrollment.objects.count(), 0)
        for path in file_paths:
            self.assertFalse(os.path.exists(path), path)

    def test_students_cannot_use_teacher_pages(self):
        self.client.force_login(make_student())
        self.assertEqual(self.client.get(reverse("courses:teacher_create")).status_code, 403)
        self.assertEqual(self.client.post(reverse("courses:teacher_create"), self.data).status_code, 403)
        self.assertEqual(Course.objects.count(), 0)

    def test_unknown_course_id(self):
        self.assertEqual(self.client.get(reverse("courses:teacher_edit", args=[99999])).status_code, 404)

    def test_pending_teacher_cannot_reach_teacher_pages(self):
        pending = make_teacher("pending@example.com", approved=False)
        self.client.force_login(pending)  # force_login bypasses the login rule; the session is not honoured
        self.assertEqual(self.client.get(reverse("courses:teacher_list")).status_code, 302)


class EnrolledStudentsTests(TestCase):  # UC11
    def test_only_own_courses_students_with_name_email_date(self):
        teacher, other = make_teacher("t1@example.com"), make_teacher("t2@example.com")
        mine, theirs = make_course(teacher, "Mine"), make_course(other, "Theirs")
        ann, bob = make_student("ann@example.com", name="Ann Lee"), make_student("bob@example.com", name="Bob Ray")
        enroll(ann, mine)
        enroll(bob, theirs)
        self.client.force_login(teacher)
        response = self.client.get(reverse("courses:teacher_students", args=[mine.pk]))
        self.assertContains(response, "Ann Lee")
        self.assertContains(response, "ann@example.com")
        self.assertNotContains(response, "bob@example.com")
        self.assertContains(response, Enrollment.objects.get(student=ann).enrolled_at.strftime("%Y"))
        self.assertEqual(self.client.get(reverse("courses:teacher_students", args=[theirs.pk])).status_code, 404)

    def test_empty_state(self):
        teacher = make_teacher()
        course = make_course(teacher)
        self.client.force_login(teacher)
        self.assertContains(self.client.get(reverse("courses:teacher_students", args=[course.pk])), "No students have enrolled")


class AdminCourseTests(MediaTestCase):  # UC5
    def setUp(self):
        self.admin = make_admin()
        self.teacher = make_teacher()
        self.course = make_course(self.teacher, "Algebra", "Math")
        self.client.force_login(self.admin)

    def test_list_shows_title_category_teacher(self):
        response = self.client.get(reverse("courses:admin_list"))
        self.assertContains(response, "Algebra")
        self.assertContains(response, "Math")
        self.assertContains(response, self.teacher.name)

    def test_detail_shows_materials(self):
        make_material(self.course, "Week 1 notes")
        self.assertContains(self.client.get(reverse("courses:admin_detail", args=[self.course.pk])), "Week 1 notes")

    def test_hide_requires_confirmation_then_hides(self):
        url = reverse("courses:admin_hide", args=[self.course.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.course.refresh_from_db()
        self.assertTrue(self.course.is_published)
        self.client.post(url)
        self.course.refresh_from_db()
        self.assertEqual(self.course.visibility, Course.Visibility.HIDDEN)

    def test_publish_hidden_course(self):
        self.course.visibility = "hidden"
        self.course.save()
        self.client.post(reverse("courses:admin_publish", args=[self.course.pk]))
        self.course.refresh_from_db()
        self.assertTrue(self.course.is_published)

    def test_repeating_a_transition_is_an_error(self):
        response = self.client.post(reverse("courses:admin_publish", args=[self.course.pk]), follow=True)
        self.assertContains(response, "already published")

    def test_remove_after_confirmation(self):
        url = reverse("courses:admin_remove", args=[self.course.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(Course.objects.exists())
        self.client.post(url)
        self.assertFalse(Course.objects.exists())

    def test_teachers_and_students_cannot_manage_courses(self):
        for user in (self.teacher, make_student()):
            self.client.force_login(user)
            for name in ("courses:admin_hide", "courses:admin_publish", "courses:admin_remove"):
                self.assertEqual(self.client.post(reverse(name, args=[self.course.pk])).status_code, 403)
        self.course.refresh_from_db()
        self.assertTrue(self.course.is_published)

    def test_hidden_course_is_not_accessible_to_students(self):
        student = make_student()
        enroll(student, self.course)
        material = make_material(self.course)
        self.client.post(reverse("courses:admin_hide", args=[self.course.pk]))
        self.client.force_login(student)
        self.assertNotContains(self.client.get(reverse("courses:browse")), "Algebra")
        self.assertEqual(self.client.get(reverse("courses:detail", args=[self.course.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("courses:open_course", args=[self.course.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("materials:file", args=[material.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("courses:my_courses")), "Algebra")

    def test_removed_course_is_gone_for_students(self):
        student = make_student()
        self.client.post(reverse("courses:admin_remove", args=[self.course.pk]))
        self.client.force_login(student)
        self.assertEqual(self.client.get(reverse("courses:detail", args=[self.course.pk])).status_code, 404)


class BrowseSearchTests(MediaTestCase):  # UC13
    def setUp(self):
        teacher = make_teacher()
        self.python = make_course(teacher, "Python Basics", "Programming", description="Learn loops and functions")
        self.algebra = make_course(teacher, "Linear Algebra", "Mathematics", description="Vectors and matrices")
        self.hidden = make_course(teacher, "Secret Course", "Programming", visibility="hidden")
        self.student = make_student()
        self.client.force_login(self.student)
        self.url = reverse("courses:browse")

    def test_lists_published_only_with_teacher_and_category(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Python Basics")
        self.assertContains(response, "Linear Algebra")
        self.assertContains(response, "Programming")
        self.assertContains(response, self.python.teacher.name)
        self.assertNotContains(response, "Secret Course")

    def test_search_by_title(self):
        response = self.client.get(self.url, {"q": "python"})
        self.assertContains(response, "Python Basics")
        self.assertNotContains(response, "Linear Algebra")

    def test_search_by_keyword_in_description(self):
        response = self.client.get(self.url, {"q": "matrices"})
        self.assertContains(response, "Linear Algebra")
        self.assertNotContains(response, "Python Basics")

    def test_filter_by_category(self):
        response = self.client.get(self.url, {"category": "Mathematics"})
        self.assertContains(response, "Linear Algebra")
        self.assertNotContains(response, "Python Basics")

    def test_search_and_category_combine(self):
        response = self.client.get(self.url, {"q": "python", "category": "Mathematics"})
        self.assertContains(response, "No Courses Found")

    def test_no_courses_found_message(self):
        response = self.client.get(self.url, {"q": "zzzzzz"})
        self.assertContains(response, "No Courses Found")

    def test_hidden_course_is_not_found_by_search(self):
        self.assertContains(self.client.get(self.url, {"q": "secret"}), "No Courses Found")

    def test_pagination(self):
        teacher = make_teacher("many@example.com")
        for i in range(15):
            make_course(teacher, f"Bulk {i:02d}", "Bulk")
        with override_settings(PAGE_SIZE=5):
            response = self.client.get(self.url, {"category": "Bulk"})
            self.assertEqual(len(response.context["page"].object_list), 5)
            self.assertTrue(response.context["page"].has_next())
            second = self.client.get(self.url, {"category": "Bulk", "page": 2})
            self.assertEqual(len(second.context["page"].object_list), 5)

    def test_search_keeps_filters_across_pages(self):
        teacher = make_teacher("many@example.com")
        for i in range(6):
            make_course(teacher, f"Bulk {i}", "Bulk")
        with override_settings(PAGE_SIZE=2):
            response = self.client.get(self.url, {"category": "Bulk"})
        self.assertContains(response, "category=Bulk&amp;page=2")

    def test_thumbnails_are_served_through_a_permission_checked_view(self):
        course = make_course(self.python.teacher, "With image")
        course.thumbnail.save("t.png", png_file(), save=True)
        response = self.client.get(reverse("courses:thumbnail", args=[course.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        b"".join(response.streaming_content)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("courses:thumbnail", args=[course.pk])).status_code, 302)

    def test_hidden_course_thumbnail_only_for_owner_and_admin(self):
        self.hidden.thumbnail.save("t.png", png_file(), save=True)
        url = reverse("courses:thumbnail", args=[self.hidden.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.hidden.teacher)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)


class EnrollmentTests(TestCase):  # UC14
    def setUp(self):
        self.teacher = make_teacher()
        self.course = make_course(self.teacher)
        self.student = make_student()
        self.client.force_login(self.student)

    def test_detail_shows_enroll_button_when_not_enrolled(self):
        response = self.client.get(reverse("courses:detail", args=[self.course.pk]))
        self.assertContains(response, "Enroll")
        self.assertNotContains(response, "Open Course")

    def test_enroll_creates_record_and_shows_success(self):
        response = self.client.post(reverse("courses:enroll", args=[self.course.pk]), follow=True)
        self.assertEqual(Enrollment.objects.filter(student=self.student, course=self.course).count(), 1)
        self.assertContains(response, "You are now enrolled")
        self.assertContains(response, "Open Course")
        self.assertContains(self.client.get(reverse("courses:my_courses")), self.course.title)

    def test_duplicate_enrollment_is_prevented(self):
        url = reverse("courses:enroll", args=[self.course.pk])
        self.client.post(url)
        response = self.client.post(url, follow=True)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertContains(response, "already enrolled")

    def test_database_constraint_prevents_duplicates(self):
        enroll(self.student, self.course)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Enrollment.objects.create(student=self.student, course=self.course)

    def test_service_reports_existing_enrollment(self):
        self.assertTrue(services.enroll_student(self.student, self.course))
        self.assertFalse(services.enroll_student(self.student, self.course))

    def test_cannot_enroll_in_hidden_course(self):
        self.course.visibility = "hidden"
        self.course.save()
        response = self.client.post(reverse("courses:enroll", args=[self.course.pk]), follow=True)
        self.assertEqual(Enrollment.objects.count(), 0)
        self.assertContains(response, "not available")

    def test_enrolling_requires_post(self):
        self.assertEqual(self.client.get(reverse("courses:enroll", args=[self.course.pk])).status_code, 405)
        self.assertEqual(Enrollment.objects.count(), 0)

    def test_only_students_can_enroll(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.post(reverse("courses:enroll", args=[self.course.pk])).status_code, 403)
        self.assertEqual(Enrollment.objects.count(), 0)

    def test_enroll_unknown_course(self):
        self.assertEqual(self.client.post(reverse("courses:enroll", args=[99999])).status_code, 404)

    def test_enrolled_course_page_shows_open_course(self):
        enroll(self.student, self.course)
        self.assertContains(self.client.get(reverse("courses:detail", args=[self.course.pk])), "Open Course")

    def test_open_course_requires_enrollment(self):
        self.assertEqual(self.client.get(reverse("courses:open_course", args=[self.course.pk])).status_code, 403)
        enroll(self.student, self.course)
        self.assertEqual(self.client.get(reverse("courses:open_course", args=[self.course.pk])).status_code, 200)
