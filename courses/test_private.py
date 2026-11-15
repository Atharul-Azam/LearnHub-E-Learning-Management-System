"""Public / private courses, invitation links, access requests, favourites, discovery, sharing."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.factories import (
    MediaTestCase,
    enroll,
    make_assignment,
    make_course,
    make_material,
    make_student,
    make_teacher,
)
from notifications.models import Notification

from . import private
from .models import Course, CourseAccessRequest, Enrollment, Favourite


class PrivateCourseBase(MediaTestCase):
    def setUp(self):
        self.teacher = make_teacher("t@example.com", name="Tina")
        self.other_teacher = make_teacher("t2@example.com", name="Other")
        self.student = make_student("s@example.com", name="Sam")
        self.outsider = make_student("o@example.com", name="Olga")
        self.public = make_course(self.teacher, "Public Course")
        self.course = make_course(self.teacher, "Secret Course", access="private")
        private.sync_access(self.course)
        self.course.refresh_from_db()
        self.material = make_material(self.course)
        self.assignment = make_assignment(self.course)

    def login(self, user):
        self.client.force_login(user)


class VisibilityTests(PrivateCourseBase):
    def test_private_course_gets_a_secure_token_and_public_does_not(self):
        self.assertTrue(self.course.invite_token)
        self.assertGreaterEqual(len(self.course.invite_token), 40)
        self.assertIsNone(self.public.invite_token)

    def test_tokens_are_unique_and_random(self):
        other = make_course(self.teacher, "Another", access="private")
        private.sync_access(other)
        self.assertNotEqual(other.invite_token, self.course.invite_token)

    def test_public_courses_are_listed_private_are_not(self):
        self.login(self.student)
        response = self.client.get(reverse("courses:browse"))
        self.assertContains(response, "Public Course")
        self.assertNotContains(response, "Secret Course")

    def test_private_course_not_findable_by_search(self):
        self.login(self.student)
        self.assertNotContains(self.client.get(reverse("courses:browse"), {"q": "Secret"}), "Secret Course")

    def test_private_course_detail_is_404_for_unauthorised_student(self):
        self.login(self.outsider)
        self.assertEqual(self.client.get(reverse("courses:detail", args=[self.course.pk])).status_code, 404)

    def test_unauthorised_student_cannot_open_content_by_url(self):
        self.login(self.outsider)
        for url in (
            reverse("courses:open_course", args=[self.course.pk]),
            reverse("materials:file", args=[self.material.pk]),
            reverse("assignments:student_detail", args=[self.assignment.pk]),
            reverse("progress:course_progress", args=[self.course.pk]),
            reverse("community:student_course", args=[self.course.pk]),
        ):
            self.assertIn(self.client.get(url).status_code, (403, 404), url)

    def test_direct_enrol_into_private_course_is_refused(self):
        self.login(self.outsider)
        response = self.client.post(reverse("courses:enroll", args=[self.course.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Enrollment.objects.filter(course=self.course).exists())

    def test_service_refuses_private_enrolment(self):
        from core.services import BusinessRuleError
        from .services import enroll_student

        with self.assertRaises(BusinessRuleError):
            enroll_student(self.outsider, self.course)

    def test_private_thumbnail_is_not_public(self):
        from core.factories import png_file

        self.course.thumbnail.save("t.png", png_file(), save=True)
        self.login(self.outsider)
        self.assertEqual(self.client.get(reverse("courses:thumbnail", args=[self.course.pk])).status_code, 404)
        enroll(self.student, self.course)
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("courses:thumbnail", args=[self.course.pk])).status_code, 200)

    def test_public_course_is_open_to_any_student_and_enrol_works(self):
        self.login(self.outsider)
        self.assertEqual(self.client.get(reverse("courses:detail", args=[self.public.pk])).status_code, 200)
        self.client.post(reverse("courses:enroll", args=[self.public.pk]))
        self.assertTrue(Enrollment.objects.filter(student=self.outsider, course=self.public).exists())

    def test_enrolled_student_sees_private_course_in_my_courses_and_detail(self):
        enroll(self.student, self.course)
        self.login(self.student)
        self.assertContains(self.client.get(reverse("courses:my_courses")), "Secret Course")
        self.assertEqual(self.client.get(reverse("courses:detail", args=[self.course.pk])).status_code, 200)

    def test_switching_to_private_keeps_enrolled_students_and_creates_token(self):
        enroll(self.student, self.public)
        self.login(self.teacher)
        self.client.post(
            reverse("courses:teacher_edit", args=[self.public.pk]),
            {"title": "Public Course", "description": "d", "category": "Programming", "access": "private"},
        )
        self.public.refresh_from_db()
        self.assertEqual(self.public.access, "private")
        self.assertTrue(self.public.invite_token)
        self.assertTrue(Enrollment.objects.filter(student=self.student, course=self.public).exists())

    def test_switching_to_public_removes_the_token(self):
        self.login(self.teacher)
        self.client.post(
            reverse("courses:teacher_edit", args=[self.course.pk]),
            {"title": "Secret Course", "description": "d", "category": "Programming", "access": "public"},
        )
        self.course.refresh_from_db()
        self.assertIsNone(self.course.invite_token)

    def test_editing_without_access_field_keeps_current_type(self):
        self.login(self.teacher)
        self.client.post(
            reverse("courses:teacher_edit", args=[self.course.pk]),
            {"title": "Secret Course", "description": "d", "category": "Programming"},
        )
        self.course.refresh_from_db()
        self.assertEqual(self.course.access, "private")

    def test_new_course_can_be_created_private(self):
        self.login(self.teacher)
        self.client.post(
            reverse("courses:teacher_create"),
            {"title": "New private", "description": "d", "category": "X", "access": "private"},
        )
        course = Course.objects.get(title="New private")
        self.assertEqual(course.access, "private")
        self.assertTrue(course.invite_token)

    def test_hidden_private_course_link_is_invalid(self):
        Course.objects.filter(pk=self.course.pk).update(visibility="hidden")
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("courses:join", args=[self.course.invite_token])).status_code, 404)


class InvitationAndRequestTests(PrivateCourseBase):
    def join_url(self, token=None):
        return reverse("courses:join", args=[token or self.course.invite_token])

    def test_link_shows_basic_info_but_no_content(self):
        self.login(self.student)
        response = self.client.get(self.join_url())
        self.assertContains(response, "Secret Course")
        self.assertContains(response, "Request access")
        self.assertNotContains(response, self.material.title)
        self.assertNotContains(response, self.assignment.title)

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(self.join_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_teacher_and_other_roles_cannot_use_the_student_join_page(self):
        self.login(self.other_teacher)
        self.assertEqual(self.client.get(self.join_url()).status_code, 403)

    def test_invalid_and_expired_tokens(self):
        self.login(self.student)
        self.assertEqual(self.client.get(self.join_url("nonsense-token")).status_code, 404)
        Course.objects.filter(pk=self.course.pk).update(invite_expires_at=timezone.now() - timedelta(minutes=1))
        response = self.client.get(self.join_url())
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "expired", status_code=404)

    def test_public_course_cannot_be_joined_with_a_token(self):
        Course.objects.filter(pk=self.public.pk).update(invite_token="x" * 43)
        self.login(self.student)
        self.assertEqual(self.client.get(self.join_url("x" * 43)).status_code, 404)

    def test_request_access_creates_pending_request_and_notifies_teacher(self):
        self.login(self.student)
        self.client.post(self.join_url())
        request = CourseAccessRequest.objects.get(student=self.student)
        self.assertEqual(request.status, "pending")
        self.assertFalse(Enrollment.objects.filter(student=self.student, course=self.course).exists())
        note = Notification.objects.get(recipient=self.teacher)
        self.assertIn("requested access", note.message)

    def test_duplicate_request_is_prevented(self):
        self.login(self.student)
        self.client.post(self.join_url())
        response = self.client.post(self.join_url(), follow=True)
        self.assertContains(response, "already requested")
        self.assertEqual(CourseAccessRequest.objects.filter(student=self.student).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.teacher).count(), 1)

    def test_database_rejects_duplicate_requests(self):
        CourseAccessRequest.objects.create(course=self.course, student=self.student)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CourseAccessRequest.objects.create(course=self.course, student=self.student)

    def test_teacher_approves_and_student_gets_access(self):
        self.login(self.student)
        self.client.post(self.join_url())
        request = CourseAccessRequest.objects.get()
        self.login(self.teacher)
        self.client.post(reverse("courses:request_approve", args=[request.pk]))
        request.refresh_from_db()
        self.assertEqual(request.status, "approved")
        self.assertTrue(Enrollment.objects.filter(student=self.student, course=self.course).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.student, message__contains="approved").exists())
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("courses:open_course", args=[self.course.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("materials:file", args=[self.material.pk])).status_code, 200)

    def test_teacher_rejects_and_student_stays_locked_out(self):
        self.login(self.student)
        self.client.post(self.join_url())
        request = CourseAccessRequest.objects.get()
        self.login(self.teacher)
        self.client.post(reverse("courses:request_reject", args=[request.pk]))
        request.refresh_from_db()
        self.assertEqual(request.status, "rejected")
        self.login(self.student)
        self.assertIn(self.client.get(reverse("courses:open_course", args=[self.course.pk])).status_code, (403, 404))
        response = self.client.post(self.join_url(), follow=True)
        self.assertContains(response, "rejected")
        self.assertEqual(CourseAccessRequest.objects.count(), 1)

    def test_other_teacher_cannot_decide_requests(self):
        self.login(self.student)
        self.client.post(self.join_url())
        request = CourseAccessRequest.objects.get()
        self.login(self.other_teacher)
        self.client.post(reverse("courses:request_approve", args=[request.pk]))
        request.refresh_from_db()
        self.assertEqual(request.status, "pending")
        self.assertFalse(Enrollment.objects.exists())

    def test_student_cannot_approve_their_own_request(self):
        self.login(self.student)
        self.client.post(self.join_url())
        request = CourseAccessRequest.objects.get()
        self.assertEqual(self.client.post(reverse("courses:request_approve", args=[request.pk])).status_code, 403)

    def test_decision_urls_do_nothing_on_get(self):
        request = CourseAccessRequest.objects.create(course=self.course, student=self.student)
        self.login(self.teacher)
        self.client.get(reverse("courses:request_approve", args=[request.pk]))
        request.refresh_from_db()
        self.assertEqual(request.status, "pending")

    def test_pending_requests_show_in_teacher_dashboard_and_list(self):
        CourseAccessRequest.objects.create(course=self.course, student=self.student)
        self.login(self.teacher)
        self.assertEqual(self.client.get(reverse("dashboards:teacher")).context["pending_requests"], 1)
        self.assertContains(self.client.get(reverse("courses:teacher_requests_all")), "Sam")
        self.assertContains(self.client.get(reverse("courses:teacher_requests", args=[self.course.pk])), "Sam")

    def test_teacher_only_sees_requests_for_own_courses(self):
        CourseAccessRequest.objects.create(course=self.course, student=self.student)
        self.login(self.other_teacher)
        self.assertNotContains(self.client.get(reverse("courses:teacher_requests_all")), "Sam")
        self.assertEqual(self.client.get(reverse("courses:teacher_requests", args=[self.course.pk])).status_code, 404)

    def test_revoke_removes_access_and_keeps_submissions(self):
        from core.factories import make_submission
        from assignments.models import Submission

        enroll(self.student, self.course)
        submission = make_submission(self.assignment, self.student)
        self.login(self.teacher)
        url = reverse("courses:student_revoke", args=[self.course.pk, self.student.pk])
        self.assertEqual(self.client.get(url).status_code, 200)  # confirmation page, nothing changed yet
        self.assertTrue(Enrollment.objects.filter(student=self.student).exists())
        self.client.post(url)
        self.assertFalse(Enrollment.objects.filter(student=self.student).exists())
        self.assertEqual(CourseAccessRequest.objects.get(student=self.student).status, "revoked")
        self.assertTrue(Submission.objects.filter(pk=submission.pk).exists())
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("courses:open_course", args=[self.course.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("courses:detail", args=[self.course.pk])).status_code, 404)

    def test_revoked_student_can_be_approved_again(self):
        enroll(self.student, self.course)
        private.revoke_student(self.teacher, self.course, self.student)
        request = CourseAccessRequest.objects.get()
        private.approve_request(self.teacher, request.pk)
        self.assertTrue(Enrollment.objects.filter(student=self.student, course=self.course).exists())

    def test_other_teacher_cannot_revoke(self):
        enroll(self.student, self.course)
        self.login(self.other_teacher)
        self.assertEqual(self.client.post(reverse("courses:student_revoke", args=[self.course.pk, self.student.pk])).status_code, 404)
        self.assertTrue(Enrollment.objects.filter(student=self.student).exists())

    def test_already_enrolled_student_is_redirected_into_the_course(self):
        enroll(self.student, self.course)
        self.login(self.student)
        self.assertRedirects(self.client.get(self.join_url()), reverse("courses:open_course", args=[self.course.pk]), fetch_redirect_response=False)


class InviteManagementTests(PrivateCourseBase):
    def test_regenerate_invalidates_old_link(self):
        old = self.course.invite_token
        self.login(self.teacher)
        self.client.post(reverse("courses:teacher_sharing", args=[self.course.pk]), {"action": "generate", "expiry": "7"})
        self.course.refresh_from_db()
        self.assertNotEqual(self.course.invite_token, old)
        self.assertIsNotNone(self.course.invite_expires_at)
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("courses:join", args=[old])).status_code, 404)
        self.assertEqual(self.client.get(reverse("courses:join", args=[self.course.invite_token])).status_code, 200)

    def test_disable_link(self):
        old = self.course.invite_token
        self.login(self.teacher)
        self.client.post(reverse("courses:teacher_sharing", args=[self.course.pk]), {"action": "disable"})
        self.course.refresh_from_db()
        self.assertIsNone(self.course.invite_token)
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("courses:join", args=[old])).status_code, 404)

    def test_cannot_generate_invite_for_public_course(self):
        self.login(self.teacher)
        self.client.post(reverse("courses:teacher_sharing", args=[self.public.pk]), {"action": "generate"})
        self.public.refresh_from_db()
        self.assertIsNone(self.public.invite_token)

    def test_only_owner_can_open_sharing_page(self):
        self.login(self.other_teacher)
        self.assertEqual(self.client.get(reverse("courses:teacher_sharing", args=[self.course.pk])).status_code, 404)
        self.login(self.student)
        self.assertEqual(self.client.get(reverse("courses:teacher_sharing", args=[self.course.pk])).status_code, 403)

    def test_sharing_page_shows_invitation_link_for_private_and_detail_link_for_public(self):
        self.login(self.teacher)
        self.assertContains(self.client.get(reverse("courses:teacher_sharing", args=[self.course.pk])), self.course.invite_token)
        self.assertContains(self.client.get(reverse("courses:teacher_sharing", args=[self.public.pk])), reverse("courses:detail", args=[self.public.pk]))


class StudentSharingTests(PrivateCourseBase):
    def test_public_course_detail_offers_copyable_link(self):
        self.login(self.student)
        response = self.client.get(reverse("courses:detail", args=[self.public.pk]))
        self.assertContains(response, "data-copy-button")
        self.assertContains(response, reverse("courses:detail", args=[self.public.pk]))

    def test_private_course_never_exposes_content_link_or_token_to_students(self):
        enroll(self.student, self.course)
        self.login(self.student)
        for url in (reverse("courses:detail", args=[self.course.pk]), reverse("courses:open_course", args=[self.course.pk])):
            response = self.client.get(url)
            self.assertNotContains(response, "data-copy-button")
            self.assertNotContains(response, self.course.invite_token)

    def test_shared_public_link_requires_login_then_works(self):
        url = reverse("courses:detail", args=[self.public.pk])
        self.assertEqual(self.client.get(url).status_code, 302)


class FavouriteTests(PrivateCourseBase):
    def test_add_and_remove_favourite(self):
        self.login(self.student)
        url = reverse("courses:favourite_toggle", args=[self.public.pk])
        self.client.post(url)
        self.assertTrue(Favourite.objects.filter(student=self.student, course=self.public).exists())
        self.assertContains(self.client.get(reverse("courses:favourites")), "Public Course")
        self.client.post(url)
        self.assertFalse(Favourite.objects.exists())

    def test_database_prevents_duplicate_favourites(self):
        Favourite.objects.create(student=self.student, course=self.public)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Favourite.objects.create(student=self.student, course=self.public)

    def test_cannot_favourite_a_private_course_without_access(self):
        self.login(self.outsider)
        self.assertEqual(self.client.post(reverse("courses:favourite_toggle", args=[self.course.pk])).status_code, 404)
        self.assertFalse(Favourite.objects.exists())

    def test_favourite_of_private_course_disappears_when_access_is_revoked(self):
        enroll(self.student, self.course)
        Favourite.objects.create(student=self.student, course=self.course)
        private.revoke_student(self.teacher, self.course, self.student)
        self.login(self.student)
        self.assertNotContains(self.client.get(reverse("courses:favourites")), "Secret Course")

    def test_public_favourite_can_be_shared_but_private_one_cannot(self):
        enroll(self.student, self.course)
        Favourite.objects.create(student=self.student, course=self.public)
        Favourite.objects.create(student=self.student, course=self.course)
        self.login(self.student)
        response = self.client.get(reverse("courses:favourites"))
        self.assertContains(response, "data-copy-button", count=1)
        self.assertNotContains(response, self.course.invite_token)

    def test_favourites_are_per_student(self):
        Favourite.objects.create(student=self.student, course=self.public)
        self.login(self.outsider)
        self.assertNotContains(self.client.get(reverse("courses:favourites")), "Public Course")

    def test_teacher_cannot_use_favourites(self):
        self.login(self.teacher)
        self.assertEqual(self.client.post(reverse("courses:favourite_toggle", args=[self.public.pk])).status_code, 403)

    def test_open_redirect_in_next_is_ignored(self):
        self.login(self.student)
        response = self.client.post(reverse("courses:favourite_toggle", args=[self.public.pk]), {"next": "//evil.example/"})
        self.assertEqual(response["Location"], reverse("courses:detail", args=[self.public.pk]))


class DiscoveryTests(PrivateCourseBase):
    def setUp(self):
        super().setUp()
        self.older = make_course(self.other_teacher, "Alpha Algebra", category="Math")
        Course.objects.filter(pk=self.older.pk).update(created_at=timezone.now() - timedelta(days=30))
        self.login(self.student)

    def titles(self, **params):
        response = self.client.get(reverse("courses:browse"), params)
        return [c.title for c in response.context["page"]]

    def test_search_and_category_filters(self):
        self.assertEqual(self.titles(q="algebra"), ["Alpha Algebra"])
        self.assertEqual(self.titles(category="Math"), ["Alpha Algebra"])

    def test_there_is_no_teacher_filter(self):
        response = self.client.get(reverse("courses:browse"))
        self.assertNotContains(response, 'name="teacher"')
        self.assertNotContains(response, "All teachers")
        self.assertNotIn("teachers", response.context)
        self.assertEqual(len(self.titles(teacher=self.teacher.pk)), 2)  # a leftover ?teacher= is ignored
        self.assertContains(response, "By ")  # the teacher is still shown on every course card

    def test_sorting_newest_and_oldest(self):
        self.assertEqual(self.titles(sort="newest"), ["Public Course", "Alpha Algebra"])
        self.assertEqual(self.titles(sort="oldest"), ["Alpha Algebra", "Public Course"])

    def test_invalid_sort_value_is_ignored(self):
        self.assertEqual(len(self.titles(sort="drop table")), 2)

    def test_empty_state_message(self):
        self.assertContains(self.client.get(reverse("courses:browse"), {"q": "zzzz"}), "No Courses Found")

    def test_pagination(self):
        for i in range(15):
            make_course(self.teacher, f"Bulk {i}")
        response = self.client.get(reverse("courses:browse"))
        self.assertTrue(response.context["page"].has_next())

    def test_recently_viewed_tracking(self):
        enroll(self.student, self.public)
        self.client.get(reverse("courses:open_course", args=[self.public.pk]))
        self.assertIsNotNone(Enrollment.objects.get(student=self.student).last_accessed_at)
        response = self.client.get(reverse("dashboards:student"))
        self.assertEqual(len(response.context["recent_courses"]), 1)


class MigrationDefaultsTests(TestCase):
    def test_new_course_defaults_to_public(self):
        course = make_course(make_teacher("t@example.com"))
        self.assertEqual(course.access, Course.Access.PUBLIC)
