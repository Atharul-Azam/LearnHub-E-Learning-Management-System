import os
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from core.factories import (
    MediaTestCase,
    enroll,
    fake_file,
    make_admin,
    make_assignment,
    make_course,
    make_student,
    make_submission,
    make_teacher,
    pdf_file,
    txt_file,
)
from courses.models import Enrollment

from .models import Assignment, Submission


def form_deadline(delta=timedelta(days=3)):
    return (timezone.localtime() + delta).strftime("%Y-%m-%dT%H:%M")


class AssignmentManagementTests(MediaTestCase):  # UC10
    def setUp(self):
        self.teacher = make_teacher("t1@example.com")
        self.other = make_teacher("t2@example.com")
        self.course = make_course(self.teacher)
        self.client.force_login(self.teacher)
        self.url = reverse("assignments:teacher_add", args=[self.course.pk])
        self.data = {"title": "Essay", "instructions": "Write 500 words.", "deadline": form_deadline(), "max_marks": 20}

    def test_create_assignment(self):
        response = self.client.post(self.url, self.data)
        self.assertRedirects(response, reverse("courses:teacher_detail", args=[self.course.pk]))
        assignment = Assignment.objects.get()
        self.assertEqual((assignment.course, assignment.title, assignment.max_marks), (self.course, "Essay", 20))
        self.assertFalse(assignment.attachment)

    def test_create_with_optional_attachment(self):
        self.data["attachment"] = pdf_file("brief.pdf")
        self.client.post(self.url, self.data)
        assignment = Assignment.objects.get()
        self.assertEqual(assignment.attachment_name, "brief.pdf")
        self.assertTrue(os.path.exists(assignment.attachment.path))

    def test_invalid_input(self):
        bad = [
            {"title": ""},
            {"instructions": "  "},
            {"deadline": "not a date"},
            {"deadline": ""},
            {"max_marks": 0},
            {"max_marks": -5},
            {"max_marks": ""},
            {"max_marks": "abc"},
            {"attachment": fake_file("evil.exe")},
            {"attachment": fake_file("fake.pdf")},
        ]
        for override in bad:
            response = self.client.post(self.url, dict(self.data, **override))
            self.assertEqual(response.status_code, 200, override)
            self.assertTrue(response.context["form"].errors, override)
        self.assertEqual(Assignment.objects.count(), 0)

    def test_edit_and_attachment_replacement(self):
        assignment = make_assignment(self.course)
        url = reverse("assignments:teacher_edit", args=[assignment.pk])
        self.client.post(url, dict(self.data, attachment=pdf_file("a.pdf")))
        assignment.refresh_from_db()
        first = assignment.attachment.path
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, dict(self.data, title="Edited", attachment=txt_file("b.txt")))
        assignment.refresh_from_db()
        self.assertEqual((assignment.title, assignment.attachment_name), ("Edited", "b.txt"))
        self.assertFalse(os.path.exists(first))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, dict(self.data, remove_attachment="on"))
        assignment.refresh_from_db()
        self.assertFalse(assignment.attachment)

    def test_cannot_lower_max_marks_below_awarded_marks(self):
        assignment = make_assignment(self.course, max_marks=10)
        submission = make_submission(assignment, make_student())
        submission.marks, submission.reviewed = Decimal("9"), True
        submission.save()
        response = self.client.post(reverse("assignments:teacher_edit", args=[assignment.pk]), dict(self.data, max_marks=5))
        self.assertContains(response, "cannot be lower than marks already awarded")
        assignment.refresh_from_db()
        self.assertEqual(assignment.max_marks, 10)

    def test_delete_requires_confirmation_and_removes_submissions_and_files(self):
        assignment = make_assignment(self.course)
        submission = make_submission(assignment, make_student())
        path = submission.file.path
        url = reverse("assignments:teacher_delete", args=[assignment.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(Assignment.objects.exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url)
        self.assertFalse(Assignment.objects.exists())
        self.assertFalse(Submission.objects.exists())
        self.assertFalse(os.path.exists(path))

    def test_other_teacher_cannot_create_edit_delete_or_review(self):
        assignment = make_assignment(self.course)
        submission = make_submission(assignment, make_student())
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.url, self.data).status_code, 404)
        for name, obj in (("assignments:teacher_edit", assignment), ("assignments:teacher_delete", assignment), ("assignments:teacher_detail", assignment), ("assignments:review", submission)):
            self.assertEqual(self.client.get(reverse(name, args=[obj.pk])).status_code, 404, name)
        self.assertEqual(self.client.post(reverse("assignments:teacher_delete", args=[assignment.pk])).status_code, 404)
        self.assertEqual(Assignment.objects.count(), 1)

    def test_students_cannot_manage_assignments(self):
        self.client.force_login(make_student())
        self.assertEqual(self.client.post(self.url, self.data).status_code, 403)

    def test_enrolled_student_sees_assignment_and_attachment_others_do_not(self):
        self.data["attachment"] = pdf_file("brief.pdf")
        self.client.post(self.url, self.data)
        assignment = Assignment.objects.get()
        student, outsider = make_student("in@example.com"), make_student("out@example.com")
        enroll(student, self.course)
        self.client.force_login(student)
        page = self.client.get(reverse("assignments:student_detail", args=[assignment.pk]))
        self.assertContains(page, "Essay")
        self.assertContains(page, "Download attachment")
        download = self.client.get(reverse("assignments:attachment", args=[assignment.pk]))
        self.assertEqual(download.status_code, 200)
        b"".join(download.streaming_content)
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("assignments:student_detail", args=[assignment.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("assignments:attachment", args=[assignment.pk])).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("assignments:attachment", args=[assignment.pk])).status_code, 404)

    def test_pagination_of_submissions(self):
        assignment = make_assignment(self.course)
        for i in range(7):
            make_submission(assignment, make_student(f"s{i}@example.com"))
        with override_settings(PAGE_SIZE=3):
            response = self.client.get(reverse("assignments:teacher_detail", args=[assignment.pk]))
        self.assertEqual(len(response.context["page"].object_list), 3)
        self.assertEqual(response.context["page"].paginator.num_pages, 3)


class SubmissionTests(MediaTestCase):  # UC16
    def setUp(self):
        self.teacher = make_teacher()
        self.course = make_course(self.teacher)
        self.student = make_student("s@example.com")
        self.other_student = make_student("o@example.com")
        enroll(self.student, self.course)
        enroll(self.other_student, self.course)
        self.assignment = make_assignment(self.course, deadline=timezone.now() + timedelta(days=2))
        self.url = reverse("assignments:student_detail", args=[self.assignment.pk])
        self.client.force_login(self.student)

    def test_page_shows_deadline_and_submit_form(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Deadline")
        self.assertContains(response, "Submit Work")

    def test_on_time_submission(self):
        before = timezone.now()
        response = self.client.post(self.url, {"file": pdf_file("answer.pdf")}, follow=True)
        after = timezone.now()
        submission = Submission.objects.get()
        self.assertFalse(submission.is_late)
        self.assertEqual(submission.status, Submission.ON_TIME)
        self.assertTrue(before <= submission.submitted_at <= after)
        self.assertEqual((submission.student, submission.assignment), (self.student, self.assignment))
        self.assertTrue(os.path.exists(submission.file.path))
        self.assertTrue(submission.file.name.startswith(f"submissions/assignment_{self.assignment.pk}/"))
        self.assertContains(response, "submitted successfully")
        self.assertContains(response, "Submitted On Time")

    def test_late_submission_is_accepted_and_marked_late(self):
        self.assignment.deadline = timezone.now() - timedelta(hours=1)
        self.assignment.save()
        self.assertContains(self.client.get(self.url), "marked as late")
        response = self.client.post(self.url, {"file": pdf_file()}, follow=True)
        submission = Submission.objects.get()
        self.assertTrue(submission.is_late)
        self.assertEqual(submission.status, Submission.LATE)
        self.assertContains(response, "Submitted Late")

    def test_deadline_boundary_exactly_at_deadline_is_on_time(self):
        from unittest import mock

        deadline = timezone.now() + timedelta(minutes=5)
        self.assignment.deadline = deadline
        self.assignment.save()
        with mock.patch("assignments.services.timezone.now", return_value=deadline):
            self.client.post(self.url, {"file": pdf_file()})
        self.assertFalse(Submission.objects.get().is_late)

    def test_client_supplied_timestamp_and_lateness_are_ignored(self):
        self.assignment.deadline = timezone.now() - timedelta(days=1)
        self.assignment.save()
        self.client.post(self.url, {"file": pdf_file(), "submitted_at": "2000-01-01 00:00:00", "is_late": "", "marks": "10", "reviewed": "on"})
        submission = Submission.objects.get()
        self.assertTrue(submission.is_late)
        self.assertGreater(submission.submitted_at.year, 2020)
        self.assertIsNone(submission.marks)
        self.assertFalse(submission.reviewed)

    def test_invalid_uploads_create_nothing(self):
        bad = [fake_file("x.exe"), fake_file("x.pdf"), fake_file("x.html", b"<script>alert(1)</script>"), fake_file("empty.pdf", b"")]
        for upload in bad:
            response = self.client.post(self.url, {"file": upload})
            self.assertEqual(response.status_code, 200, upload.name)
            self.assertContains(response, "Nothing was submitted")
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Submission.objects.count(), 0)

    def test_oversized_upload_rejected(self):
        rules = {"submission": {"extensions": {"pdf"}, "max_bytes": 10}}
        with override_settings(UPLOAD_RULES=rules):
            response = self.client.post(self.url, {"file": pdf_file()})
        self.assertContains(response, "too large")
        self.assertEqual(Submission.objects.count(), 0)

    def test_second_submission_is_refused_and_original_is_untouched(self):
        self.client.post(self.url, {"file": pdf_file("first.pdf")})
        first = Submission.objects.get()
        path, stamp = first.file.path, first.submitted_at
        response = self.client.post(self.url, {"file": pdf_file("second.pdf")}, follow=True)
        self.assertContains(response, "already submitted")
        self.assertEqual(Submission.objects.count(), 1)
        first.refresh_from_db()
        self.assertEqual((first.original_name, first.file.path, first.submitted_at), ("first.pdf", path, stamp))
        self.assertTrue(os.path.exists(path))

    def test_invalid_upload_after_valid_one_does_not_change_existing_submission(self):
        self.client.post(self.url, {"file": pdf_file("first.pdf")})
        self.client.post(self.url, {"file": fake_file("bad.pdf")})
        submission = Submission.objects.get()
        self.assertEqual(submission.original_name, "first.pdf")
        self.assertEqual(submission.status, Submission.ON_TIME)

    def test_retry_after_rejected_upload_succeeds(self):
        # DD UC16 activity diagram: "Failed" returns to file selection; nothing was stored.
        self.client.post(self.url, {"file": fake_file("bad.pdf")})
        self.assertEqual(Submission.objects.count(), 0)
        self.client.post(self.url, {"file": pdf_file("good.pdf")})
        self.assertEqual(Submission.objects.get().original_name, "good.pdf")

    def test_changing_deadline_later_does_not_rewrite_lateness(self):
        # D-17: lateness is decided once, at submission time (DD 6.3 markLate()).
        self.assignment.deadline = timezone.now() - timedelta(hours=1)
        self.assignment.save()
        self.client.post(self.url, {"file": pdf_file()})
        self.assignment.deadline = timezone.now() + timedelta(days=5)
        self.assignment.save()
        self.assertTrue(Submission.objects.get().is_late)

    def test_database_enforces_one_submission_per_student_and_assignment(self):
        make_submission(self.assignment, self.student)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_submission(self.assignment, self.student)

    def test_unique_per_assignment_not_global(self):
        second = make_assignment(self.course, "Second")
        make_submission(self.assignment, self.student)
        make_submission(second, self.student)
        make_submission(self.assignment, self.other_student)
        self.assertEqual(Submission.objects.count(), 3)

    def test_not_enrolled_student_cannot_view_or_submit(self):
        outsider = make_student("out@example.com")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"file": pdf_file()}).status_code, 403)
        self.assertEqual(Submission.objects.count(), 0)

    def test_cannot_submit_to_hidden_course(self):
        self.course.visibility = "hidden"
        self.course.save()
        self.assertEqual(self.client.post(self.url, {"file": pdf_file()}).status_code, 404)
        self.assertEqual(Submission.objects.count(), 0)

    def test_teachers_cannot_use_student_submission_page(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.post(self.url, {"file": pdf_file()}).status_code, 403)

    def test_submission_updates_progress(self):
        self.client.post(self.url, {"file": pdf_file()})
        self.assertEqual(Enrollment.objects.get(student=self.student).progress, 100)  # 1 of 1 activities

    def test_submission_visible_to_owning_teacher(self):
        self.client.post(self.url, {"file": pdf_file("answer.pdf")})
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("assignments:teacher_detail", args=[self.assignment.pk]))
        self.assertContains(response, self.student.email)
        self.assertContains(response, "On time")
        self.assertContains(response, "Not reviewed")

    def test_unknown_assignment(self):
        self.assertEqual(self.client.get(reverse("assignments:student_detail", args=[99999])).status_code, 404)


class ReviewTests(MediaTestCase):  # UC12, UC17 (marks visibility)
    def setUp(self):
        self.teacher = make_teacher()
        self.course = make_course(self.teacher)
        self.student = make_student("s@example.com")
        self.other_student = make_student("o@example.com")
        enroll(self.student, self.course)
        enroll(self.other_student, self.course)
        self.assignment = make_assignment(self.course, max_marks=10)
        self.submission = make_submission(self.assignment, self.student)
        self.url = reverse("assignments:review", args=[self.submission.pk])
        self.client.force_login(self.teacher)

    def test_review_page_and_list(self):
        listing = self.client.get(reverse("assignments:teacher_detail", args=[self.assignment.pk]))
        self.assertContains(listing, "s@example.com")
        self.assertContains(listing, "Not reviewed")
        self.assertContains(listing, "View file")
        self.assertContains(self.client.get(self.url), "Maximum marks")

    def test_valid_review_marks_submission_reviewed(self):
        response = self.client.post(self.url, {"marks": "8.5", "feedback": "  Well done  "})
        self.assertRedirects(response, reverse("assignments:teacher_detail", args=[self.assignment.pk]))
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.marks, Decimal("8.50"))
        self.assertEqual(self.submission.feedback, "Well done")
        self.assertTrue(self.submission.reviewed)
        self.assertEqual(self.submission.status, Submission.REVIEWED)
        self.assertIsNotNone(self.submission.reviewed_at)

    def test_marks_boundaries(self):
        for value in ("0", "10", "10.00", "0.01"):
            self.client.post(self.url, {"marks": value, "feedback": ""})
            self.submission.refresh_from_db()
            self.assertEqual(self.submission.marks, Decimal(value), value)

    def test_invalid_marks_are_rejected_and_state_unchanged(self):
        for value in ("10.01", "11", "-1", "abc", "", "1e3", "5.123"):
            response = self.client.post(self.url, {"marks": value, "feedback": "x"})
            self.assertEqual(response.status_code, 200, value)
            self.assertTrue(response.context["form"].errors, value)
            self.submission.refresh_from_db()
            self.assertIsNone(self.submission.marks, value)
            self.assertFalse(self.submission.reviewed, value)
            self.assertEqual(self.submission.feedback, "", value)

    def test_feedback_is_optional(self):
        self.client.post(self.url, {"marks": "5"})
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.reviewed)

    def test_review_can_be_edited(self):
        self.client.post(self.url, {"marks": "5", "feedback": "ok"})
        self.client.post(self.url, {"marks": "7", "feedback": "better"})
        self.submission.refresh_from_db()
        self.assertEqual((self.submission.marks, self.submission.feedback), (Decimal("7"), "better"))
        self.assertTrue(self.submission.reviewed)

    def test_teacher_can_view_and_download_submitted_file(self):
        url = reverse("assignments:submission_file", args=[self.submission.pk])
        view = self.client.get(url)
        self.assertEqual(view.status_code, 200)
        self.assertTrue(b"".join(view.streaming_content).startswith(b"%PDF"))
        download = self.client.get(url, {"download": "1"})
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertIn("work.pdf", download["Content-Disposition"])
        b"".join(download.streaming_content)

    def test_only_owner_can_see_submission_file(self):
        url = reverse("assignments:submission_file", args=[self.submission.pk])
        denied = [make_teacher("other@example.com"), self.other_student, make_admin()]
        for user in denied:
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 404, user.email)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.student)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)

    def test_review_requires_teacher_role_and_ownership(self):
        for user in (self.student, self.other_student, make_admin()):
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.url, {"marks": "10", "feedback": "x"}).status_code, 403)
        self.client.force_login(make_teacher("other@example.com"))
        self.assertEqual(self.client.post(self.url, {"marks": "10", "feedback": "x"}).status_code, 404)
        self.submission.refresh_from_db()
        self.assertFalse(self.submission.reviewed)

    def test_unknown_submission(self):
        self.assertEqual(self.client.get(reverse("assignments:review", args=[99999])).status_code, 404)

    def test_student_sees_marks_and_feedback_only_after_review(self):
        self.client.force_login(self.student)
        page = self.client.get(reverse("assignments:student_detail", args=[self.assignment.pk]))
        self.assertContains(page, "Not Yet Reviewed")
        self.client.force_login(self.teacher)
        self.client.post(self.url, {"marks": "9", "feedback": "Great job"})
        self.client.force_login(self.student)
        page = self.client.get(reverse("assignments:student_detail", args=[self.assignment.pk]))
        self.assertContains(page, "9 / 10")
        self.assertContains(page, "Great job")
        self.assertNotContains(page, "Not Yet Reviewed")

    def test_database_constraints(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Submission.objects.filter(pk=self.submission.pk).update(reviewed=True)  # reviewed without marks
        with self.assertRaises(IntegrityError), transaction.atomic():
            Submission.objects.filter(pk=self.submission.pk).update(marks=Decimal("-1"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Assignment.objects.filter(pk=self.assignment.pk).update(max_marks=0)

    def test_review_uses_server_side_check_even_if_form_is_bypassed(self):
        from core.services import BusinessRuleError
        from .services import save_review

        with self.assertRaises(BusinessRuleError):
            save_review(self.submission, Decimal("11"), "")
        self.submission.refresh_from_db()
        self.assertFalse(self.submission.reviewed)
