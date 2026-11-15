"""Dashboards, analytics and navigation indicators."""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from core.factories import (
    MediaTestCase,
    enroll,
    make_admin,
    make_assignment,
    make_course,
    make_student,
    make_submission,
    make_teacher,
)
from courses.models import CourseAccessRequest, Enrollment


class StudentDashboardTests(MediaTestCase):
    def setUp(self):
        self.teacher = make_teacher("t@example.com", name="Tina")
        self.student = make_student("s@example.com", name="Sam")
        self.c1 = make_course(self.teacher, "Course One")
        self.c2 = make_course(self.teacher, "Course Two")
        self.e1 = enroll(self.student, self.c1)
        self.e2 = enroll(self.student, self.c2)
        Enrollment.objects.filter(pk=self.e1.pk).update(progress=100)
        Enrollment.objects.filter(pk=self.e2.pk).update(progress=40)
        self.client.force_login(self.student)

    def test_summary_figures_come_from_records(self):
        response = self.client.get(reverse("dashboards:student"))
        self.assertEqual(response.context["enrollment_total"], 2)
        self.assertEqual(response.context["completed_total"], 1)
        self.assertEqual(response.context["overall_progress"], 70)
        self.assertContains(response, self.student.public_id)
        self.assertContains(response, "Continue Learning")

    def test_pending_overdue_and_submitted_assignments(self):
        due = make_assignment(self.c1, "Due soon", deadline=timezone.now() + timedelta(days=1))
        late = make_assignment(self.c1, "Missed", deadline=timezone.now() - timedelta(days=1))
        done = make_assignment(self.c2, "Done", deadline=timezone.now() + timedelta(days=2))
        make_submission(done, self.student)
        response = self.client.get(reverse("dashboards:student"))
        pending = {a.title: a.overdue for a in response.context["pending_assignments"]}
        self.assertEqual(pending, {"Due soon": False, "Missed": True})
        self.assertEqual(response.context["pending_total"], 2)

    def test_recent_marks_show_only_own_reviewed_work(self):
        a = make_assignment(self.c1)
        sub = make_submission(a, self.student)
        other = make_student("o@example.com")
        enroll(other, self.c1)
        make_submission(a, other)
        from assignments.services import save_review

        save_review(sub, 9, "Nice")
        marks = self.client.get(reverse("dashboards:student")).context["recent_marks"]
        self.assertEqual([m.student_id for m in marks], [self.student.pk])

    def test_hidden_course_not_listed(self):
        type(self.c1).objects.filter(pk=self.c1.pk).update(visibility="hidden")
        self.assertEqual(self.client.get(reverse("dashboards:student")).context["enrollment_total"], 1)

    def test_empty_state(self):
        newbie = make_student("n@example.com")
        self.client.force_login(newbie)
        self.assertContains(self.client.get(reverse("dashboards:student")), "not enrolled in any course yet")

    def test_deadline_reminder_appears_in_notifications(self):
        make_assignment(self.c1, "Tomorrow", deadline=timezone.now() + timedelta(hours=20))
        self.client.get(reverse("dashboards:student"))
        self.assertContains(self.client.get(reverse("notifications:list")), "Deadline soon")


class TeacherDashboardAndAnalyticsTests(MediaTestCase):
    def setUp(self):
        self.teacher = make_teacher("t@example.com", name="Tina")
        self.rival = make_teacher("r@example.com", name="Rival")
        self.s1 = make_student("s1@example.com")
        self.s2 = make_student("s2@example.com")
        self.pub = make_course(self.teacher, "Public A")
        self.prv = make_course(self.teacher, "Private B", access="private")
        self.rival_course = make_course(self.rival, "Rival course")
        enroll(self.s1, self.pub)
        enroll(self.s2, self.pub)
        enroll(self.s1, self.prv)
        enroll(self.s1, self.rival_course)
        self.a = make_assignment(self.pub)
        self.sub1 = make_submission(self.a, self.s1, late=True)
        self.sub2 = make_submission(self.a, self.s2)
        from assignments.services import save_review

        save_review(self.sub2, 5, "ok")
        make_submission(make_assignment(self.rival_course), self.s1)
        CourseAccessRequest.objects.create(course=self.prv, student=self.s2)
        self.client.force_login(self.teacher)

    def test_dashboard_numbers(self):
        r = self.client.get(reverse("dashboards:teacher"))
        c = r.context
        self.assertEqual((c["course_total"], c["public_total"], c["private_total"]), (2, 1, 1))
        self.assertEqual(c["student_total"], 2)
        self.assertEqual(c["pending_requests"], 1)
        self.assertEqual(c["pending_reviews"], 1)
        self.assertContains(r, self.teacher.public_id)

    def test_analytics_numbers_are_correct_and_scoped(self):
        c = self.client.get(reverse("dashboards:analytics")).context
        self.assertEqual(c["enrollment_total"], 3)  # the rival's enrolment is not counted
        self.assertEqual(c["submission_total"], 2)
        self.assertEqual((c["pending_reviews"], c["reviewed_total"], c["late_total"]), (1, 1, 1))
        rows = {row["course"].title: row for row in c["performance"]}
        self.assertEqual(set(rows), {"Public A", "Private B"})
        self.assertEqual(rows["Public A"]["students"], 2)
        self.assertEqual(rows["Public A"]["submissions"], 2)
        self.assertEqual(rows["Public A"]["bar"], 100)

    def test_other_teacher_sees_only_their_own_figures(self):
        self.client.force_login(self.rival)
        c = self.client.get(reverse("dashboards:analytics")).context
        self.assertEqual((c["course_total"], c["enrollment_total"], c["submission_total"]), (1, 1, 1))

    def test_analytics_empty_for_new_teacher(self):
        self.client.force_login(make_teacher("new@example.com"))
        response = self.client.get(reverse("dashboards:analytics"))
        self.assertContains(response, "No courses yet")

    def test_analytics_is_teacher_only(self):
        for user in (self.s1, make_admin()):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("dashboards:analytics")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboards:analytics")).status_code, 302)

    def test_recent_activity_lists_real_events(self):
        activity = self.client.get(reverse("dashboards:teacher")).context["activity"]
        texts = " ".join(text for _, text in activity)
        self.assertIn("submitted", texts)
        self.assertIn("enrolled", texts)


class CoursePerformanceQueryTests(MediaTestCase):
    """Regression: teacher_course_performance() raised "misuse of aggregate function COUNT()" on SQLite.

    Cause: the aggregate aliases ("reviewed", "pending") were named like the Submission field
    "reviewed", so Q(reviewed=False) in the "pending" aggregate resolved to the aggregate itself.
    """

    def setUp(self):
        from assignments.models import Submission

        self.Submission = Submission
        self.teacher = make_teacher("t@example.com")
        self.rival = make_teacher("r@example.com")
        self.students = [make_student(f"s{i}@example.com") for i in range(1, 5)]
        self.busy = make_course(self.teacher, "Busy")          # 2 assignments, 4 submissions: 3 reviewed, 1 pending
        self.quiet = make_course(self.teacher, "Quiet")        # assignment but no submissions
        self.empty = make_course(self.teacher, "Empty")        # no assignments at all
        self.waiting = make_course(self.teacher, "Waiting")    # only unreviewed submissions
        self.rival_course = make_course(self.rival, "Rival")
        for student in self.students:
            enroll(student, self.busy)
        enroll(self.students[0], self.waiting)
        a1, a2 = make_assignment(self.busy, "A1"), make_assignment(self.busy, "A2")
        make_assignment(self.quiet, "Q1")
        w1 = make_assignment(self.waiting, "W1")
        subs = [make_submission(a1, s) for s in self.students[:3]] + [make_submission(a2, self.students[0])]
        for sub in subs[:3]:
            self.Submission.objects.filter(pk=sub.pk).update(reviewed=True, marks=5)
        make_submission(w1, self.students[0])
        make_submission(make_assignment(self.rival_course, "R1"), self.students[1])  # must never be counted

    def rows(self, teacher=None):
        from dashboards.stats import teacher_course_performance

        return {r["course"].title: r for r in teacher_course_performance(teacher or self.teacher)}

    def test_query_executes_and_counts_each_course(self):
        rows = self.rows()
        self.assertEqual(set(rows), {"Busy", "Quiet", "Empty", "Waiting"})
        busy = rows["Busy"]
        self.assertEqual((busy["submissions"], busy["reviewed"], busy["pending"]), (4, 3, 1))
        self.assertEqual((busy["students"], busy["assignments"]), (4, 2))
        self.assertEqual(rows["Waiting"]["submissions"], 1)
        self.assertEqual((rows["Waiting"]["reviewed"], rows["Waiting"]["pending"]), (0, 1))

    def test_courses_without_submissions_show_zero_not_missing(self):
        rows = self.rows()
        for title in ("Quiet", "Empty"):
            self.assertEqual((rows[title]["submissions"], rows[title]["reviewed"], rows[title]["pending"]), (0, 0, 0), title)
        self.assertEqual(rows["Quiet"]["assignments"], 1)
        self.assertEqual(rows["Empty"]["assignments"], 0)

    def test_total_equals_reviewed_plus_pending_everywhere(self):
        for title, row in self.rows().items():
            self.assertEqual(row["submissions"], row["reviewed"] + row["pending"], title)

    def test_other_teachers_submissions_are_not_counted(self):
        self.assertEqual(sum(r["submissions"] for r in self.rows().values()), 5)
        rival = self.rows(self.rival)
        self.assertEqual((rival["Rival"]["submissions"], rival["Rival"]["pending"]), (1, 1))

    def test_figures_match_the_summary_totals(self):
        from dashboards.stats import teacher_totals

        rows, totals = self.rows(), teacher_totals(self.teacher)
        self.assertEqual(sum(r["submissions"] for r in rows.values()), totals["submission_total"])
        self.assertEqual(sum(r["reviewed"] for r in rows.values()), totals["reviewed_total"])
        self.assertEqual(sum(r["pending"] for r in rows.values()), totals["pending_reviews"])

    def test_dashboard_and_analytics_pages_load_and_show_the_figures(self):
        self.client.force_login(self.teacher)
        dashboard = self.client.get(reverse("dashboards:teacher"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "4 submissions, 1 to review")
        analytics = self.client.get(reverse("dashboards:analytics"))
        self.assertEqual(analytics.status_code, 200)
        self.assertContains(analytics, "Busy")

    def test_new_teacher_without_courses_gets_an_empty_list(self):
        self.assertEqual(self.rows(make_teacher("new@example.com")), {})


class NavigationTests(MediaTestCase):
    def setUp(self):
        self.teacher = make_teacher("t@example.com")
        self.student = make_student("s@example.com")
        self.course = make_course(self.teacher)
        enroll(self.student, self.course)

    def active(self, response):
        return [i["label"] for i in response.context["nav_items"] if i["active"]]

    def test_exactly_one_active_tab_for_each_student_page(self):
        self.client.force_login(self.student)
        expected = {
            reverse("dashboards:student"): "Dashboard",
            reverse("courses:browse"): "Browse Courses",
            reverse("courses:detail", args=[self.course.pk]): "Browse Courses",
            reverse("courses:my_courses"): "My Courses",
            reverse("courses:open_course", args=[self.course.pk]): "My Courses",
            reverse("progress:course_progress", args=[self.course.pk]): "My Courses",
            reverse("community:student_course", args=[self.course.pk]): "My Courses",
            reverse("courses:favourites"): "Favourites",
        }
        for url, label in expected.items():
            self.assertEqual(self.active(self.client.get(url)), [label], url)

    def test_teacher_nested_pages_highlight_my_courses(self):
        self.client.force_login(self.teacher)
        for url in (
            reverse("courses:teacher_list"),
            reverse("courses:teacher_detail", args=[self.course.pk]),
            reverse("courses:teacher_students", args=[self.course.pk]),
            reverse("courses:teacher_sharing", args=[self.course.pk]),
            reverse("materials:add", args=[self.course.pk]),
            reverse("assignments:teacher_add", args=[self.course.pk]),
            reverse("community:teacher_course", args=[self.course.pk]),
        ):
            self.assertEqual(self.active(self.client.get(url)), ["My Courses"], url)
        self.assertEqual(self.active(self.client.get(reverse("dashboards:analytics"))), ["Analytics"])
        self.assertEqual(self.active(self.client.get(reverse("courses:teacher_requests_all"))), ["Requests"])
        self.assertEqual(self.active(self.client.get(reverse("courses:teacher_create"))), ["Create Course"])

    def test_active_tab_is_rendered_with_aria_current_and_survives_refresh(self):
        self.client.force_login(self.student)
        for _ in range(2):
            response = self.client.get(reverse("courses:browse"))
            self.assertContains(response, 'aria-current="page"')

    def test_admin_tabs(self):
        self.client.force_login(make_admin())
        self.assertEqual(self.active(self.client.get(reverse("courses:admin_list"))), ["Courses"])
        self.assertEqual(self.active(self.client.get(reverse("accounts:user_list"))), ["Users"])
        # The Admin interface has no Discussion section any more.
        self.assertNotContains(self.client.get(reverse("accounts:user_list")), "Discussions")

    def test_settings_pages_have_settings_section(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("accounts:settings_appearance")).context["nav_section"], "settings")

    def test_anonymous_has_no_navigation_items(self):
        self.assertNotContains(self.client.get(reverse("accounts:login")), "nav-link-active")

    def test_mobile_menu_toggle_and_skip_link_present(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("dashboards:student"))
        self.assertContains(response, "data-nav-toggle")
        self.assertContains(response, "Skip to content")
