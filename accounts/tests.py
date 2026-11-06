from datetime import timedelta

from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.factories import PASSWORD, make_admin, make_course, make_student, make_teacher, make_user, enroll

from .models import User


class RegistrationTests(TestCase):  # UC1
    url = None

    def setUp(self):
        self.url = reverse("accounts:register")
        self.data = {"account_type": "student", "name": "Ann Lee", "email": "ann@example.com", "password": "Passw0rd123"}

    def test_register_form_offers_student_and_teacher(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Student")
        self.assertContains(response, "Teacher")

    def test_student_registration_is_active_and_password_is_hashed(self):
        response = self.client.post(self.url, self.data)
        self.assertRedirects(response, reverse("accounts:login"))
        user = User.objects.get(email="ann@example.com")
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertEqual(user.status, User.Status.ACTIVE)
        self.assertNotEqual(user.password, "Passw0rd123")
        self.assertTrue(user.password.startswith(("pbkdf2_", "argon2", "bcrypt", "scrypt")))
        self.assertTrue(user.check_password("Passw0rd123"))

    def test_student_registration_shows_success_message(self):
        response = self.client.post(self.url, self.data, follow=True)
        self.assertContains(response, "student account was created")

    def test_teacher_registration_is_pending_with_waiting_message(self):
        self.data.update(account_type="teacher", email="t@example.com")
        response = self.client.post(self.url, self.data, follow=True)
        user = User.objects.get(email="t@example.com")
        self.assertEqual(user.role, User.Role.TEACHER)
        self.assertEqual(user.status, User.Status.PENDING)
        self.assertContains(response, "waiting for administrator approval")

    def test_duplicate_email_is_rejected_case_insensitively(self):
        make_student("ann@example.com")
        self.data["email"] = "ANN@Example.com"
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.filter(email__iexact="ann@example.com").count(), 1)

    def test_required_fields(self):
        for missing in ("name", "email", "password", "account_type"):
            data = dict(self.data)
            data[missing] = ""
            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, 200, missing)
            self.assertFalse(User.objects.filter(email="ann@example.com").exists(), missing)
            self.assertTrue(response.context["form"].errors, missing)

    def test_invalid_email_format(self):
        self.data["email"] = "not-an-email"
        response = self.client.post(self.url, self.data)
        self.assertContains(response, "valid e-mail")
        self.assertEqual(User.objects.count(), 0)

    def test_password_rules(self):
        cases = {"short1A": "at least 8", "onlyletters": "letters and numbers", "12345678": "letters and numbers"}
        for password, expected in cases.items():
            self.data["password"] = password
            response = self.client.post(self.url, self.data)
            self.assertEqual(response.status_code, 200, password)
            self.assertContains(response, expected)
            self.assertEqual(User.objects.count(), 0, password)

    def test_password_of_exactly_eight_letters_and_digits_is_accepted(self):
        self.data["password"] = "abcd1234"
        self.client.post(self.url, self.data)
        self.assertTrue(User.objects.filter(email="ann@example.com").exists())

    def test_cannot_register_as_admin(self):
        self.data["account_type"] = "admin"
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)


class LoginTests(TestCase):  # UC2
    def setUp(self):
        self.url = reverse("accounts:login")
        self.student = make_student("s@example.com")
        self.teacher = make_teacher("t@example.com")
        self.admin = make_admin("a@example.com")

    def login(self, email, password=PASSWORD):
        return self.client.post(self.url, {"email": email, "password": password})

    def test_role_specific_dashboards(self):
        for email, name in (("s@example.com", "dashboards:student"), ("t@example.com", "dashboards:teacher"), ("a@example.com", "dashboards:admin")):
            self.client.logout()
            response = self.login(email)
            self.assertRedirects(response, reverse("dashboards:home"), fetch_redirect_response=False)
            self.assertRedirects(self.client.get(reverse("dashboards:home")), reverse(name), fetch_redirect_response=False)
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_email_login_is_case_insensitive(self):
        response = self.login("S@Example.COM")
        self.assertRedirects(response, reverse("dashboards:home"), fetch_redirect_response=False)

    def test_wrong_password_and_unknown_email_give_identical_generic_error(self):
        wrong_password = self.login("s@example.com", "WrongPass123")
        unknown_email = self.login("nobody@example.com", PASSWORD)
        for response in (wrong_password, unknown_email):
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "The e-mail address or password is incorrect.")
        self.assertEqual(
            list(wrong_password.context["form"].non_field_errors()),
            list(unknown_email.context["form"].non_field_errors()),
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_pending_teacher_cannot_login_and_is_told_why(self):
        make_teacher("p@example.com", approved=False)
        response = self.login("p@example.com")
        self.assertContains(response, "waiting for administrator approval")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_rejected_teacher_cannot_login(self):
        make_user("r@example.com", role="teacher", status="rejected")
        response = self.login("r@example.com")
        self.assertContains(response, "rejected")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_deactivated_account_cannot_login(self):
        make_user("d@example.com", role="student", status="deactivated")
        response = self.login("d@example.com")
        self.assertContains(response, "deactivated")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_status_is_not_revealed_when_password_is_wrong(self):
        make_teacher("p@example.com", approved=False)
        response = self.login("p@example.com", "WrongPass123")
        self.assertContains(response, "The e-mail address or password is incorrect.")
        self.assertNotContains(response, "waiting for administrator approval")

    def test_open_redirect_is_not_followed(self):
        response = self.client.post(self.url, {"email": "s@example.com", "password": PASSWORD, "next": "https://evil.example/"})
        self.assertRedirects(response, reverse("dashboards:home"), fetch_redirect_response=False)

    def test_safe_next_is_followed(self):
        target = reverse("courses:browse")
        response = self.client.post(self.url, {"email": "s@example.com", "password": PASSWORD, "next": target})
        self.assertRedirects(response, target, fetch_redirect_response=False)

    def test_logout_requires_post_and_ends_session(self):
        self.login("s@example.com")
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, self.url)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("dashboards:student")).status_code, 302)

    def test_login_page_redirects_authenticated_user(self):
        self.login("s@example.com")
        self.assertRedirects(self.client.get(self.url), reverse("dashboards:home"), fetch_redirect_response=False)


class SessionAndAccessTests(TestCase):  # UC2 session states, SRS 21
    def setUp(self):
        self.student = make_student()

    def test_session_expires_after_inactivity(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("dashboards:student")).status_code, 200)
        Session.objects.update(expire_date=timezone.now() - timedelta(seconds=1))
        response = self.client.get(reverse("dashboards:student"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('dashboards:student')}")

    @override_settings(SESSION_COOKIE_AGE=120)
    def test_inactivity_timeout_is_configurable(self):
        self.client.post(reverse("accounts:login"), {"email": self.student.email, "password": PASSWORD})
        remaining = Session.objects.get().expire_date - timezone.now()
        self.assertLessEqual(remaining, timedelta(seconds=120))
        self.assertGreater(remaining, timedelta(seconds=100))

    def test_session_is_renewed_on_activity(self):
        from django.conf import settings

        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.client.force_login(self.student)
        Session.objects.update(expire_date=timezone.now() + timedelta(seconds=30))
        self.client.get(reverse("dashboards:student"))
        self.assertGreater(Session.objects.get().expire_date, timezone.now() + timedelta(seconds=600))

    def test_deactivating_a_logged_in_user_ends_access(self):
        self.client.force_login(self.student)
        User.objects.filter(pk=self.student.pk).update(status=User.Status.DEACTIVATED)
        response = self.client.get(reverse("dashboards:student"))
        self.assertEqual(response.status_code, 302)

    def test_anonymous_users_are_sent_to_login(self):
        for name in ("dashboards:home", "dashboards:admin", "courses:browse", "courses:teacher_list", "accounts:user_list"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("accounts:login"), response["Location"], name)

    def test_each_role_is_blocked_from_other_roles_dashboards(self):
        teacher = make_teacher()
        admin = make_admin()
        matrix = {
            self.student: ("dashboards:admin", "dashboards:teacher", "courses:teacher_list", "accounts:user_list", "courses:admin_list"),
            teacher: ("dashboards:admin", "dashboards:student", "courses:browse", "courses:my_courses", "accounts:teacher_requests"),
            admin: ("dashboards:teacher", "dashboards:student", "courses:teacher_list", "courses:browse"),
        }
        for user, urls in matrix.items():
            self.client.force_login(user)
            for name in urls:
                self.assertEqual(self.client.get(reverse(name)).status_code, 403, f"{user.role} -> {name}")
            self.client.logout()


class AdminTeacherApprovalTests(TestCase):  # UC3
    def setUp(self):
        self.admin = make_admin()
        self.teacher = make_teacher("pending@example.com", approved=False)
        self.client.force_login(self.admin)

    def test_pending_list_and_details(self):
        response = self.client.get(reverse("accounts:teacher_requests"))
        self.assertContains(response, "pending@example.com")
        detail = self.client.get(reverse("accounts:teacher_request_detail", args=[self.teacher.pk]))
        self.assertContains(detail, "pending@example.com")

    def test_confirmation_page_changes_nothing(self):
        response = self.client.get(reverse("accounts:approve_teacher", args=[self.teacher.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approve")
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.status, User.Status.PENDING)

    def test_approve_updates_status_removes_from_pending_and_allows_login(self):
        response = self.client.post(reverse("accounts:approve_teacher", args=[self.teacher.pk]))
        self.assertRedirects(response, reverse("accounts:teacher_requests"))
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.status, User.Status.ACTIVE)
        self.assertEqual(self.teacher.decided_by, self.admin)
        self.assertIsNotNone(self.teacher.decided_at)
        self.assertNotContains(self.client.get(reverse("accounts:teacher_requests")), "pending@example.com")
        self.client.logout()
        login = self.client.post(reverse("accounts:login"), {"email": "pending@example.com", "password": PASSWORD})
        self.assertRedirects(login, reverse("dashboards:home"), fetch_redirect_response=False)

    def test_reject_updates_status_and_blocks_login(self):
        self.client.post(reverse("accounts:reject_teacher", args=[self.teacher.pk]))
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.status, User.Status.REJECTED)
        self.assertNotContains(self.client.get(reverse("accounts:teacher_requests")), "pending@example.com")
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {"email": "pending@example.com", "password": PASSWORD})
        self.assertContains(response, "rejected")

    def test_processed_request_cannot_be_decided_again(self):
        self.client.post(reverse("accounts:reject_teacher", args=[self.teacher.pk]))
        response = self.client.post(reverse("accounts:approve_teacher", args=[self.teacher.pk]), follow=True)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.status, User.Status.REJECTED)
        self.assertContains(response, "cannot be changed")

    def test_students_cannot_be_approved_as_teachers(self):
        student = make_student()
        self.assertEqual(self.client.post(reverse("accounts:approve_teacher", args=[student.pk])).status_code, 404)

    def test_non_admins_cannot_decide(self):
        for user in (make_teacher("other@example.com"), make_student()):
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse("accounts:approve_teacher", args=[self.teacher.pk])).status_code, 403)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.status, User.Status.PENDING)

    def test_unknown_id_is_404(self):
        self.assertEqual(self.client.get(reverse("accounts:teacher_request_detail", args=[99999])).status_code, 404)


class AdminUserManagementTests(TestCase):  # UC4
    def setUp(self):
        self.admin = make_admin()
        self.student = make_student("stu@example.com")
        self.teacher = make_teacher("tea@example.com")
        self.client.force_login(self.admin)

    def test_list_shows_students_and_teachers_but_not_admins(self):
        response = self.client.get(reverse("accounts:user_list"))
        self.assertContains(response, "stu@example.com")
        self.assertContains(response, "tea@example.com")
        self.assertNotContains(response, "admin@example.com</td>")

    def test_filter_and_search(self):
        response = self.client.get(reverse("accounts:user_list"), {"role": "teacher"})
        self.assertContains(response, "tea@example.com")
        self.assertNotContains(response, "stu@example.com")
        response = self.client.get(reverse("accounts:user_list"), {"q": "stu@"})
        self.assertContains(response, "stu@example.com")
        self.assertNotContains(response, "tea@example.com")

    def test_account_details(self):
        self.assertContains(self.client.get(reverse("accounts:user_detail", args=[self.student.pk])), "stu@example.com")

    def test_deactivate_then_activate(self):
        url = reverse("accounts:deactivate_user", args=[self.student.pk])
        self.assertEqual(self.client.get(url).status_code, 200)  # confirmation page only
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, User.Status.ACTIVE)
        response = self.client.post(url, follow=True)
        self.assertContains(response, "was deactivated")
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, User.Status.DEACTIVATED)
        self.client.post(reverse("accounts:activate_user", args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, User.Status.ACTIVE)

    def test_invalid_transitions_are_rejected(self):
        response = self.client.post(reverse("accounts:activate_user", args=[self.student.pk]), follow=True)  # already active
        self.assertContains(response, "cannot be changed")
        rejected = make_user("rej@example.com", role="teacher", status="rejected")
        self.client.post(reverse("accounts:activate_user", args=[rejected.pk]))
        rejected.refresh_from_db()
        self.assertEqual(rejected.status, User.Status.REJECTED)

    def test_remove_requires_confirmation_then_deletes(self):
        url = reverse("accounts:remove_user", args=[self.student.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.student.pk).exists())
        response = self.client.post(url, follow=True)
        self.assertContains(response, "was removed")
        self.assertFalse(User.objects.filter(pk=self.student.pk).exists())

    def test_removing_student_removes_their_enrollment(self):
        course = make_course(self.teacher)
        enroll(self.student, course)
        self.client.post(reverse("accounts:remove_user", args=[self.student.pk]))
        self.assertEqual(course.enrollments.count(), 0)

    def test_teacher_with_courses_cannot_be_removed(self):
        make_course(self.teacher)
        response = self.client.post(reverse("accounts:remove_user", args=[self.teacher.pk]), follow=True)
        self.assertContains(response, "still owns courses")
        self.assertTrue(User.objects.filter(pk=self.teacher.pk).exists())

    def test_pending_teacher_cannot_be_removed(self):
        pending = make_teacher("pend@example.com", approved=False)
        self.client.post(reverse("accounts:remove_user", args=[pending.pk]))
        self.assertTrue(User.objects.filter(pk=pending.pk).exists())

    def test_admin_accounts_are_not_manageable(self):
        for name in ("accounts:user_detail", "accounts:deactivate_user", "accounts:remove_user"):
            self.assertEqual(self.client.post(reverse(name, args=[self.admin.pk])).status_code, 404, name)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.status, User.Status.ACTIVE)

    def test_non_admin_cannot_manage(self):
        self.client.force_login(self.teacher)
        for name in ("accounts:deactivate_user", "accounts:remove_user"):
            self.assertEqual(self.client.post(reverse(name, args=[self.student.pk])).status_code, 403)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, User.Status.ACTIVE)


class UserModelTests(TestCase):
    def test_only_active_accounts_are_active(self):
        self.assertTrue(make_student("a@example.com").is_active)
        self.assertFalse(make_teacher("b@example.com", approved=False).is_active)
        self.assertFalse(make_user("c@example.com", status="deactivated").is_active)
        self.assertFalse(make_user("d@example.com", role="teacher", status="rejected").is_active)

    def test_superuser_is_active_admin(self):
        admin = make_admin()
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.is_active)

    def test_email_is_normalised_to_lowercase(self):
        self.assertEqual(make_student("MiXed@Example.com").email, "mixed@example.com")
