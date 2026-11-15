from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assignments import services as assignment_services
from core.factories import (
    MediaTestCase,
    enroll,
    make_assignment,
    make_course,
    make_student,
    make_submission,
    make_teacher,
    pdf_file,
)

from . import services
from .models import Notification


class NotificationServiceTests(TestCase):
    def setUp(self):
        self.student = make_student("s@example.com")

    def test_notify_creates_once_per_event(self):
        first = services.notify(self.student, "courses", "Hello", "/x/", "evt:1")
        second = services.notify(self.student, "courses", "Hello again", "/x/", "evt:1")
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(Notification.objects.count(), 1)

    def test_same_event_notifies_different_users_separately(self):
        other = make_student("o@example.com")
        services.notify(self.student, "courses", "Hi", "/x/", "evt:1")
        services.notify(other, "courses", "Hi", "/x/", "evt:1")
        self.assertEqual(Notification.objects.count(), 2)

    def test_preferences_switch_categories_off(self):
        self.student.notify_assignments = False
        self.student.save()
        self.assertIsNone(services.notify(self.student, "assignments", "x", "/", "k"))
        self.assertIsNotNone(services.notify(self.student, "courses", "x", "/", "k2"))

    def test_inactive_recipient_gets_nothing(self):
        unverified = make_student("u@example.com", verified=False)
        self.assertIsNone(services.notify(unverified, "courses", "x", "/", "k"))

    def test_fallback_dedupe_key_fits_the_column(self):
        note = services.notify(self.student, "courses", "m" * 300, "/u" * 100)
        self.assertLessEqual(len(note.dedupe_key), 120)


class NotificationViewTests(TestCase):
    def setUp(self):
        self.student = make_student("s@example.com")
        self.other = make_student("o@example.com")
        self.note = services.notify(self.student, "courses", "Approved", "/my-courses/", "a")
        self.client.force_login(self.student)

    def test_list_and_unread_count_in_navigation(self):
        response = self.client.get(reverse("notifications:list"))
        self.assertContains(response, "Approved")
        self.assertEqual(response.context["nav_unread"], 1)

    def test_open_marks_read_and_redirects_to_target(self):
        response = self.client.post(reverse("notifications:open", args=[self.note.pk]))
        self.assertRedirects(response, "/my-courses/", fetch_redirect_response=False)
        self.note.refresh_from_db()
        self.assertTrue(self.note.is_read)

    def test_open_requires_post(self):
        self.client.get(reverse("notifications:open", args=[self.note.pk]))
        self.note.refresh_from_db()
        self.assertFalse(self.note.is_read)

    def test_cannot_open_someone_elses_notification(self):
        self.client.force_login(self.other)
        self.client.post(reverse("notifications:open", args=[self.note.pk]))
        self.note.refresh_from_db()
        self.assertFalse(self.note.is_read)

    def test_external_url_is_never_followed(self):
        evil = services.notify(self.student, "courses", "x", "https://evil.example/", "e")
        response = self.client.post(reverse("notifications:open", args=[evil.pk]))
        self.assertRedirects(response, reverse("notifications:list"), fetch_redirect_response=False)

    def test_mark_all_read_and_history_kept(self):
        services.notify(self.student, "courses", "Second", "/", "b")
        self.client.post(reverse("notifications:read_all"))
        self.assertEqual(services.unread_count(self.student), 0)
        self.assertEqual(Notification.objects.filter(recipient=self.student).count(), 2)
        self.assertContains(self.client.get(reverse("notifications:list")), "Second")

    def test_mark_all_read_does_not_touch_other_users(self):
        other_note = services.notify(self.other, "courses", "Theirs", "/", "z")
        self.client.post(reverse("notifications:read_all"))
        other_note.refresh_from_db()
        self.assertFalse(other_note.is_read)

    def test_unread_filter(self):
        self.client.post(reverse("notifications:open", args=[self.note.pk]))
        response = self.client.get(reverse("notifications:list"), {"filter": "unread"})
        self.assertNotContains(response, "Approved")

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("notifications:list")).status_code, 302)


class EventNotificationTests(MediaTestCase):
    def setUp(self):
        self.teacher = make_teacher("t@example.com")
        self.student = make_student("s@example.com")
        self.course = make_course(self.teacher)
        enroll(self.student, self.course)

    def test_new_assignment_notifies_enrolled_students_only_once(self):
        outsider = make_student("o@example.com")
        assignment = make_assignment(self.course)
        assignment_services.notify_new_assignment(assignment)
        assignment_services.notify_new_assignment(assignment)
        self.assertEqual(Notification.objects.filter(recipient=self.student).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=outsider).count(), 0)

    def test_publishing_through_the_view_notifies(self):
        self.client.force_login(self.teacher)
        self.client.post(
            reverse("assignments:teacher_add", args=[self.course.pk]),
            {"title": "HW", "instructions": "do", "deadline": (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"), "max_marks": "10"},
        )
        self.assertTrue(Notification.objects.filter(recipient=self.student, message__contains="HW").exists())

    def test_submission_notifies_teacher(self):
        assignment = make_assignment(self.course)
        assignment_services.submit_assignment(self.student, assignment, pdf_file())
        self.assertTrue(Notification.objects.filter(recipient=self.teacher, message__contains="submitted").exists())

    def test_review_notifies_student_once_even_if_edited(self):
        assignment = make_assignment(self.course)
        submission = make_submission(assignment, self.student)
        assignment_services.save_review(submission, 7, "Good")
        assignment_services.save_review(submission, 8, "Better")
        notes = Notification.objects.filter(recipient=self.student, message__contains="Marks published")
        self.assertEqual(notes.count(), 1)
        self.assertIn("feedback", notes.first().message)

    def test_deadline_reminder_for_unsubmitted_assignment_within_48h(self):
        soon = make_assignment(self.course, "Soon", deadline=timezone.now() + timedelta(hours=10))
        make_assignment(self.course, "Later", deadline=timezone.now() + timedelta(days=10))
        done = make_assignment(self.course, "Done", deadline=timezone.now() + timedelta(hours=5))
        make_submission(done, self.student)
        services.generate_deadline_reminders(self.student)
        services.generate_deadline_reminders(self.student)  # no duplicates
        messages = list(Notification.objects.filter(recipient=self.student).values_list("message", flat=True))
        self.assertEqual(len(messages), 1)
        self.assertIn("Soon", messages[0])

    def test_enrolment_notifies_teacher(self):
        newcomer = make_student("n@example.com")
        from courses.services import enroll_student

        enroll_student(newcomer, self.course)
        self.assertTrue(Notification.objects.filter(recipient=self.teacher, message__contains="enrolled").exists())
