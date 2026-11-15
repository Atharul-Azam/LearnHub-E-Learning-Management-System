"""Tests for ``manage.py seed_demo_data`` (written, not yet executed - see docs/TEST_REPORT.md)."""
import io
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from assignments.models import Assignment, Submission
from community.models import Announcement, Post
from core import demo_data as plan
from core.demo_files import make_avatar, make_pdf
from core.factories import make_course, make_student, make_teacher
from courses.models import Course, CourseAccessRequest, Enrollment, Favourite
from materials.models import LearningMaterial
from notifications.models import Notification
from progress.models import MaterialAccess

PASSWORD = "Test-Only-Seed-Pass-1"
MEDIA = tempfile.mkdtemp(prefix="learnhub-seed-test-media-")
CREDS = Path(tempfile.mkdtemp(prefix="learnhub-seed-test-creds-")) / "creds.local.md"
DEMO = "@" + plan.DEMO_DOMAIN


def seed(*extra, stdout=None):
    call_command("seed_demo_data", f"--password={PASSWORD}", f"--credentials-file={CREDS}", *extra,
                 stdout=stdout or io.StringIO(), stderr=io.StringIO())


def table_counts():
    return {m.__name__: m.objects.count() for m in (
        User, Course, Enrollment, CourseAccessRequest, Favourite, LearningMaterial, Assignment, Submission,
        MaterialAccess, Announcement, Post, Notification)}


class DemoPlanTests(SimpleTestCase):
    """The static plan and the file generators (no database needed)."""

    def test_plan_meets_the_requested_sizes(self):
        self.assertGreaterEqual(len(plan.TEACHERS), 15)
        self.assertGreaterEqual(plan.STUDENT_COUNT, 50)
        self.assertGreaterEqual(len(plan.PUBLIC_COURSE_INDEXES), 10)
        self.assertGreaterEqual(len(plan.PRIVATE_COURSE_INDEXES), 5)
        self.assertGreaterEqual(len(plan.COURSES), 15)

    def test_emails_and_names_are_unique_and_demo_only(self):
        emails = [plan.teacher_email(n) for n in range(1, len(plan.TEACHERS) + 1)]
        emails += [plan.pending_teacher_email(n) for n in range(1, len(plan.PENDING_TEACHERS) + 1)]
        emails += [plan.student_email(n) for n in range(1, plan.STUDENT_COUNT + 1)] + [plan.ADMIN_EMAIL]
        self.assertEqual(len(emails), len(set(emails)))
        self.assertTrue(all(e.endswith(DEMO) for e in emails))
        self.assertTrue(plan.DEMO_DOMAIN.endswith(".test"))  # reserved TLD: can never receive mail
        names = {plan.student_name(i) for i in range(plan.STUDENT_COUNT)}
        self.assertEqual(len(names), plan.STUDENT_COUNT)

    def test_generated_files_are_valid(self):
        self.assertTrue(make_pdf("Title", ["a"]).startswith(b"%PDF-"))
        self.assertTrue(make_avatar("Dr. A B", (1, 2, 3)).startswith(b"\x89PNG"))

    def test_student_one_sees_every_private_state(self):
        states = [plan.private_state(0, p) for p in range(len(plan.PRIVATE_COURSE_INDEXES))]
        self.assertEqual(set(states), {"approved", "pending", "rejected", "revoked", None})


@override_settings(DEBUG=True, MEDIA_ROOT=MEDIA)
class SeedDemoDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # "Real" data that existed before seeding and must survive it unchanged.
        cls.real_student = make_student("real.student@example.com", verified=False)
        cls.real_student.set_password("Real-Password-9")
        cls.real_student.save()
        cls.real_teacher = make_teacher("real.teacher@example.com")
        cls.real_course = make_course(cls.real_teacher, title="A Real Course")
        cls.real_hash = User.objects.get(pk=cls.real_student.pk).password
        before_mail = len(getattr(mail, "outbox", []))
        seed()
        cls.mail_sent_by_seed = len(getattr(mail, "outbox", [])) - before_mail
        cls.counts_after_first_run = table_counts()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    # ---- accounts -------------------------------------------------------------
    def test_teachers_are_approved_verified_and_have_unique_ids(self):
        teachers = User.objects.filter(email__endswith=DEMO, role="teacher", status="active")
        self.assertGreaterEqual(teachers.count(), 15)
        self.assertFalse(teachers.exclude(email_verified=True).exists())
        self.assertFalse(teachers.exclude(public_id__startswith="TCH-").exists())
        ids = list(teachers.values_list("public_id", flat=True))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(t.is_active for t in teachers))

    def test_students_are_verified_and_have_unique_ids(self):
        students = User.objects.filter(email__endswith=DEMO, role="student")
        self.assertGreaterEqual(students.count(), 50)
        self.assertFalse(students.exclude(email_verified=True).exists())
        self.assertFalse(students.exclude(public_id__startswith="STU-").exists())
        ids = list(students.values_list("public_id", flat=True))
        self.assertEqual(len(ids), len(set(ids)))

    def test_pending_demo_teachers_wait_for_the_administrator(self):
        pending = User.objects.filter(email__endswith=DEMO, role="teacher", status="pending")
        self.assertEqual(pending.count(), len(plan.PENDING_TEACHERS))
        self.assertFalse(pending.filter(public_id__isnull=False).exists())
        self.assertFalse(any(u.is_active for u in pending))

    def test_demo_admin_exists(self):
        admin = User.objects.get(email=plan.ADMIN_EMAIL)
        self.assertEqual(admin.role, "admin")
        self.assertTrue(admin.email_verified)

    def test_no_email_is_sent_by_the_seeder(self):
        self.assertEqual(self.mail_sent_by_seed, 0)

    # ---- courses and relationships -----------------------------------------------
    def test_courses(self):
        demo_courses = Course.objects.filter(teacher__email__endswith=DEMO)
        self.assertGreaterEqual(demo_courses.count(), 15)
        self.assertGreaterEqual(demo_courses.filter(access="public").count(), 10)
        self.assertGreaterEqual(demo_courses.filter(access="private").count(), 5)
        self.assertFalse(demo_courses.exclude(thumbnail="").exists())  # covers are drawn by the interface
        self.assertFalse(demo_courses.filter(access="private", invite_token__isnull=True).exists())
        self.assertFalse(demo_courses.filter(access="public", invite_token__isnull=False).exists())
        self.assertGreaterEqual(demo_courses.order_by().values("teacher").distinct().count(), 10)

    def test_private_courses_only_have_enrolments_for_approved_requests(self):
        private = Course.objects.filter(teacher__email__endswith=DEMO, access="private")
        enrolled = set(Enrollment.objects.filter(course__in=private).values_list("course_id", "student_id"))
        approved = set(CourseAccessRequest.objects.filter(course__in=private, status="approved")
                       .values_list("course_id", "student_id"))
        self.assertEqual(enrolled, approved)
        for status in ("pending", "approved", "rejected", "revoked"):
            self.assertTrue(CourseAccessRequest.objects.filter(course__in=private, status=status).exists(), status)

    def test_student_one_scenarios(self):
        student = User.objects.get(email=plan.student_email(1))
        states = []
        for course in Course.objects.filter(access="private", teacher__email__endswith=DEMO).order_by("id"):
            request = CourseAccessRequest.objects.filter(course=course, student=student).first()
            states.append(request.status if request else None)
        self.assertEqual(sorted(s or "" for s in states), sorted(["approved", "pending", "rejected", "revoked", ""]))

    def test_activity_exists(self):
        self.assertTrue(Submission.objects.filter(reviewed=True).exists())
        self.assertTrue(Submission.objects.filter(reviewed=False).exists())
        self.assertTrue(Submission.objects.filter(is_late=True).exists())
        self.assertFalse(Submission.objects.filter(reviewed=True, marks__isnull=True).exists())
        self.assertTrue(Announcement.objects.exists())
        self.assertTrue(Post.objects.filter(parent__isnull=True).exists())
        self.assertTrue(Post.objects.filter(parent__isnull=False).exists())
        self.assertTrue(Favourite.objects.exists())
        self.assertTrue(Enrollment.objects.filter(last_accessed_at__isnull=False).exists())
        self.assertTrue(Notification.objects.filter(read_at__isnull=True).exists())
        self.assertTrue(Notification.objects.filter(read_at__isnull=False).exists())

    def test_progress_has_several_levels_and_is_consistent(self):
        progress = set(Enrollment.objects.values_list("progress", flat=True))
        self.assertIn(0, progress)
        self.assertIn(100, progress)
        self.assertTrue(any(0 < p < 100 for p in progress))

    # ---- safety ----------------------------------------------------------------------
    def test_real_users_and_data_are_untouched(self):
        student = User.objects.get(pk=self.real_student.pk)
        self.assertEqual(student.password, self.real_hash)
        self.assertFalse(student.email_verified)  # the seeder did not "verify" a real user
        self.assertTrue(Course.objects.filter(pk=self.real_course.pk, title="A Real Course").exists())
        self.assertEqual(Enrollment.objects.filter(student=student).count(), 0)
        self.assertEqual(Notification.objects.filter(recipient=student).count(), 0)

    def test_normal_registration_still_requires_verification(self):
        fresh = User.objects.create_user(email="new.person@example.com", name="New Person", password="Pass-12345-x")
        self.assertFalse(fresh.email_verified)
        self.assertFalse(fresh.is_active)

    def test_rerun_creates_no_duplicates_and_keeps_passwords(self):
        student = User.objects.get(email=plan.student_email(1))
        hash_before = student.password
        seed()
        self.assertEqual(table_counts(), self.counts_after_first_run)
        student.refresh_from_db()
        self.assertEqual(student.password, hash_before)
        self.assertTrue(student.check_password(PASSWORD))

    def test_rerun_does_not_reset_demo_passwords_unless_asked(self):
        student = User.objects.get(email=plan.student_email(2))
        student.set_password("Changed-By-Tester-1")
        student.save()
        seed()
        student.refresh_from_db()
        self.assertTrue(student.check_password("Changed-By-Tester-1"))
        seed("--reset-demo-passwords")
        student.refresh_from_db()
        self.assertTrue(student.check_password(PASSWORD))
        self.assertEqual(User.objects.get(pk=self.real_student.pk).password, self.real_hash)

    def test_check_only_reports_success_and_changes_nothing(self):
        out = io.StringIO()
        call_command("seed_demo_data", "--check-only", stdout=out)
        self.assertIn("All checks passed", out.getvalue())
        self.assertEqual(table_counts(), self.counts_after_first_run)

    def test_credentials_file_is_written_and_git_ignored(self):
        text = CREDS.read_text(encoding="utf-8")
        self.assertIn(PASSWORD, text)
        self.assertIn(plan.student_email(1), text)
        self.assertIn("DEMO_CREDENTIALS.local.md", (Path(settings.BASE_DIR) / ".gitignore").read_text())

    def test_refuses_to_run_in_production_mode(self):
        before = User.objects.count()
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                seed()
        self.assertEqual(User.objects.count(), before)

    # ---- the accounts really work ---------------------------------------------------------
    def test_demo_accounts_can_log_in_and_open_their_pages(self):
        for email in (plan.student_email(1), plan.teacher_email(1), plan.ADMIN_EMAIL):
            self.assertTrue(self.client.login(email=email, password=PASSWORD), email)
            self.client.logout()
        self.client.login(email=plan.student_email(1), password=PASSWORD)
        self.assertEqual(self.client.get(reverse("courses:browse")).status_code, 200)
        self.client.logout()
        teacher = User.objects.get(email=plan.teacher_email(1))
        self.client.login(email=teacher.email, password=PASSWORD)
        course = Course.objects.filter(teacher=teacher).first()
        self.assertEqual(self.client.get(reverse("courses:teacher_detail", args=[course.pk])).status_code, 200)
