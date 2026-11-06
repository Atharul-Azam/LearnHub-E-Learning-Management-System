from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from core.factories import (
    enroll,
    make_admin,
    make_assignment,
    make_course,
    make_student,
    make_submission,
    make_teacher,
    make_user,
    MediaTestCase,
)


class AdminStatisticsTests(TestCase):  # UC6
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def stats(self):
        return self.client.get(reverse("dashboards:admin")).context["stats"]

    def test_empty_platform_shows_zeros(self):
        self.assertEqual(self.stats(), {"students": 0, "teachers": 0, "courses": 0, "enrollments": 0, "pending_teachers": 0})

    def test_numbers_come_from_the_database_and_change_with_it(self):
        t1, t2 = make_teacher("t1@example.com"), make_teacher("t2@example.com")
        make_teacher("pending@example.com", approved=False)
        make_user("rejected@example.com", role="teacher", status="rejected")
        s1, s2 = make_student("s1@example.com"), make_student("s2@example.com")
        c1, c2, c3 = make_course(t1, "A"), make_course(t1, "B", visibility="hidden"), make_course(t2, "C")
        enroll(s1, c1)
        enroll(s1, c3)
        enroll(s2, c1)
        self.assertEqual(
            self.stats(),
            {"students": 2, "teachers": 2, "courses": 3, "enrollments": 3, "pending_teachers": 1},
        )
        # a new change is reflected on the next page load (nothing is cached or hard-coded)
        User.objects.filter(email="pending@example.com").update(status="active")
        c3.delete()
        stats = self.stats()
        self.assertEqual((stats["teachers"], stats["pending_teachers"], stats["courses"], stats["enrollments"]), (3, 0, 2, 2))

    def test_rendered_page_shows_the_values(self):
        make_student("s1@example.com")
        make_student("s2@example.com")
        make_student("s3@example.com")
        response = self.client.get(reverse("dashboards:admin"))
        self.assertContains(response, 'data-stat="students">3<')

    def test_deactivated_teacher_still_counts_as_approved(self):
        make_user("old@example.com", role="teacher", status="deactivated")
        self.assertEqual(self.stats()["teachers"], 1)

    def test_only_admin_sees_statistics(self):
        for user in (make_teacher(), make_student()):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("dashboards:admin")).status_code, 403)


class RoleDashboardTests(MediaTestCase):
    def test_teacher_dashboard_lists_only_own_courses_and_pending_reviews(self):
        teacher, other = make_teacher("t1@example.com"), make_teacher("t2@example.com")
        mine, theirs = make_course(teacher, "My Course"), make_course(other, "Their Course")
        student = make_student()
        enroll(student, mine)
        make_submission(make_assignment(mine), student)
        make_submission(make_assignment(theirs), student)
        self.client.force_login(teacher)
        response = self.client.get(reverse("dashboards:teacher"))
        self.assertContains(response, "My Course")
        self.assertNotContains(response, "Their Course")
        self.assertEqual(response.context["pending_reviews"], 1)

    def test_student_dashboard_lists_only_own_enrollments(self):
        teacher = make_teacher()
        mine, other = make_course(teacher, "Enrolled Course"), make_course(teacher, "Not Enrolled Course")
        student = make_student()
        enroll(student, mine)
        self.client.force_login(student)
        response = self.client.get(reverse("dashboards:student"))
        self.assertContains(response, "Enrolled Course")
        self.assertNotContains(response, "Not Enrolled Course")

    def test_navigation_links_match_role(self):
        self.client.force_login(make_student())
        page = self.client.get(reverse("dashboards:student"))
        self.assertContains(page, reverse("courses:browse"))
        self.assertNotContains(page, reverse("accounts:user_list"))
        self.assertNotContains(page, reverse("courses:teacher_create"))
