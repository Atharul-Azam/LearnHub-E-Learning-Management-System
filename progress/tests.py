from decimal import Decimal

from django.urls import reverse

from core.factories import (
    MediaTestCase,
    enroll,
    make_assignment,
    make_course,
    make_material,
    make_student,
    make_submission,
    make_teacher,
)

from .models import MaterialAccess
from .services import compute_progress, progress_summary, record_material_access


class ProgressCalculationTests(MediaTestCase):  # SRS 20.2, DD UC15/UC17
    def setUp(self):
        self.teacher = make_teacher()
        self.course = make_course(self.teacher)
        self.student = make_student("s@example.com")
        self.enrollment = enroll(self.student, self.course)

    def test_empty_course_is_zero(self):
        self.assertEqual(compute_progress(self.student, self.course), 0)

    def test_formula_counts_materials_opened_and_assignments_submitted(self):
        m1, m2 = make_material(self.course, "a"), make_material(self.course, "b")
        a1, a2 = make_assignment(self.course, "x"), make_assignment(self.course, "y")
        self.assertEqual(compute_progress(self.student, self.course), 0)
        record_material_access(self.student, m1)
        self.assertEqual(compute_progress(self.student, self.course), 25)
        make_submission(a1, self.student)
        self.assertEqual(compute_progress(self.student, self.course), 50)
        record_material_access(self.student, m2)
        make_submission(a2, self.student)
        self.assertEqual(compute_progress(self.student, self.course), 100)

    def test_rounding_one_of_three(self):
        for title in "abc":
            make_material(self.course, title)
        record_material_access(self.student, self.course.materials.first())
        self.assertEqual(compute_progress(self.student, self.course), 33)

    def test_repeated_access_does_not_increase_progress(self):
        material = make_material(self.course)
        make_material(self.course, "other")
        for _ in range(4):
            record_material_access(self.student, material)
        self.assertEqual(MaterialAccess.objects.count(), 1)
        self.assertEqual(compute_progress(self.student, self.course), 50)

    def test_progress_is_stored_on_enrollment(self):
        material = make_material(self.course)
        make_assignment(self.course)
        record_material_access(self.student, material)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.progress, 50)

    def test_progress_is_per_student(self):
        other = make_student("o@example.com")
        enroll(other, self.course)
        material = make_material(self.course)
        record_material_access(self.student, material)
        self.assertEqual(compute_progress(self.student, self.course), 100)
        self.assertEqual(compute_progress(other, self.course), 0)

    def test_teacher_adding_and_removing_content_recalculates_everyone(self):
        material = make_material(self.course)
        record_material_access(self.student, material)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.progress, 100)
        self.client.force_login(self.teacher)
        self.client.post(reverse("assignments:teacher_add", args=[self.course.pk]), {
            "title": "New", "instructions": "x", "deadline": "2030-01-01T10:00", "max_marks": 5,
        })
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.progress, 50)
        self.client.post(reverse("materials:delete", args=[material.pk]))
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.progress, 0)  # 0 of 1 remaining activity

    def test_summary_numbers(self):
        material = make_material(self.course)
        make_assignment(self.course)
        record_material_access(self.student, material)
        summary = progress_summary(self.student, self.course)
        self.assertEqual(
            summary,
            {"percent": 50, "materials_done": 1, "materials_total": 1, "assignments_done": 0, "assignments_total": 1},
        )


class ProgressAndMarksPageTests(MediaTestCase):  # UC17
    def setUp(self):
        self.teacher = make_teacher()
        self.course = make_course(self.teacher)
        self.ann = make_student("ann@example.com")
        self.bob = make_student("bob@example.com")
        enroll(self.ann, self.course)
        enroll(self.bob, self.course)
        self.reviewed = make_assignment(self.course, "Reviewed one", max_marks=20)
        self.waiting = make_assignment(self.course, "Waiting one")
        self.todo = make_assignment(self.course, "Todo one")
        sub = make_submission(self.reviewed, self.ann)
        sub.marks, sub.feedback, sub.reviewed = Decimal("17.5"), "Ann feedback text", True
        sub.save()
        make_submission(self.waiting, self.ann)
        bob_sub = make_submission(self.reviewed, self.bob)
        bob_sub.marks, bob_sub.feedback, bob_sub.reviewed = Decimal("3"), "Bob private feedback", True
        bob_sub.save()
        self.url = reverse("progress:course_progress", args=[self.course.pk])
        self.client.force_login(self.ann)

    def test_shows_percentage_marks_feedback_and_not_yet_reviewed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["summary"]["percent"], 67)  # 2 of 3 assignments
        self.assertContains(response, "67%")
        self.assertContains(response, "17.5 / 20")
        self.assertContains(response, "Ann feedback text")
        self.assertContains(response, "Not Yet Reviewed")
        self.assertContains(response, "Not Submitted")

    def test_never_exposes_another_students_results(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, "Bob private feedback")
        self.assertNotContains(response, "3 / 20")
        self.client.force_login(self.bob)
        response = self.client.get(self.url)
        self.assertContains(response, "Bob private feedback")
        self.assertNotContains(response, "Ann feedback text")

    def test_progress_page_requires_enrollment_and_student_role(self):
        outsider = make_student("out@example.com")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_progress_shown_on_my_courses(self):
        self.client.get(self.url)  # opening the progress page re-syncs the stored percentage
        self.assertContains(self.client.get(reverse("courses:my_courses")), "67%")

    def test_unknown_course(self):
        self.assertEqual(self.client.get(reverse("progress:course_progress", args=[99999])).status_code, 404)
