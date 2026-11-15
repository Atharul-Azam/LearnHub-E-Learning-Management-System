"""E-mail verification, Student/Teacher IDs."""
import re
from unittest import mock

from django.core import mail
from django.core.management import CommandError, call_command
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from core.factories import PASSWORD, make_admin, make_student, make_teacher, make_user

from . import verification
from .identifiers import ensure_public_id
from .models import User

REGISTER = {"account_type": "student", "name": "Ann Lee", "email": "ann@example.com", "password": "Passw0rd123"}


def link_from_outbox():
    body = mail.outbox[-1].body
    return re.search(r"https?://[^\s]+/accounts/verify/[^\s]+", body).group(0)


class VerificationFlowTests(TestCase):
    def setUp(self):
        cache.clear()

    def register(self, **over):
        return self.client.post(reverse("accounts:register"), {**REGISTER, **over})

    def test_registration_sends_a_verification_email(self):
        self.register()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ann@example.com"])
        self.assertIn("/accounts/verify/", mail.outbox[0].body)

    def test_unverified_student_cannot_log_in(self):
        self.register()
        response = self.client.post(reverse("accounts:login"), {"email": "ann@example.com", "password": "Passw0rd123"})
        self.assertContains(response, "verify your e-mail")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_verification_link_verifies_and_allows_login(self):
        self.register()
        response = self.client.get(link_from_outbox(), follow=True)
        self.assertContains(response, "e-mail address is verified")
        self.assertTrue(User.objects.get(email="ann@example.com").email_verified)
        login = self.client.post(reverse("accounts:login"), {"email": "ann@example.com", "password": "Passw0rd123"})
        self.assertRedirects(login, reverse("dashboards:home"), fetch_redirect_response=False)

    def test_link_cannot_be_reused(self):
        self.register()
        link = link_from_outbox()
        self.client.get(link)
        response = self.client.get(link, follow=True)
        self.assertContains(response, "already verified")

    def test_tampered_link_is_rejected(self):
        self.register()
        link = link_from_outbox()
        response = self.client.get(link[:-3] + "xyz", follow=True)
        self.assertContains(response, "invalid or has expired")
        self.assertFalse(User.objects.get(email="ann@example.com").email_verified)

    def test_unknown_user_id_is_rejected(self):
        response = self.client.get(reverse("accounts:verify_email", args=["MTIzNDU", "abc-def"]), follow=True)
        self.assertContains(response, "invalid or has expired")

    def test_expired_link_is_rejected(self):
        self.register()
        link = link_from_outbox()
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            response = self.client.get(link, follow=True)
        self.assertContains(response, "invalid or has expired")
        self.assertFalse(User.objects.get(email="ann@example.com").email_verified)

    def test_link_for_old_email_is_invalid_after_email_changes(self):
        user = make_user("x@example.com", verified=False)
        token = verification.token_generator.make_token(user)
        user.email = "y@example.com"
        user.save()
        self.assertFalse(verification.token_generator.check_token(user, token))

    def test_resend_sends_new_mail_for_unverified_account(self):
        self.register()
        cache.clear()
        mail.outbox.clear()
        response = self.client.post(reverse("accounts:resend_verification"), {"email": "ann@example.com"}, follow=True)
        self.assertContains(response, "If an unverified account exists")
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_is_rate_limited(self):
        self.register()
        cache.clear()
        mail.outbox.clear()
        for _ in range(3):
            self.client.post(reverse("accounts:resend_verification"), {"email": "ann@example.com"})
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_answer_is_identical_for_unknown_and_verified_accounts(self):
        make_student("v@example.com")
        a = self.client.post(reverse("accounts:resend_verification"), {"email": "v@example.com"}, follow=True)
        b = self.client.post(reverse("accounts:resend_verification"), {"email": "nobody@example.com"}, follow=True)
        self.assertContains(a, "If an unverified account exists")
        self.assertContains(b, "If an unverified account exists")
        self.assertEqual(len(mail.outbox), 0)

    def test_mail_failure_does_not_break_registration(self):
        with mock.patch("accounts.verification.send_mail", side_effect=OSError("smtp down")):
            response = self.register()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email="ann@example.com").exists())

    def test_duplicate_email_registration_is_blocked(self):
        self.register()
        response = self.register(email="ANN@example.com")
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.filter(email__iexact="ann@example.com").count(), 1)

    def test_teacher_needs_both_verification_and_approval(self):
        self.register(account_type="teacher", email="t@example.com")
        teacher = User.objects.get(email="t@example.com")
        login = lambda: self.client.post(reverse("accounts:login"), {"email": "t@example.com", "password": "Passw0rd123"})
        self.assertContains(login(), "verify your e-mail")
        self.client.get(link_from_outbox())
        self.assertContains(login(), "waiting for administrator approval")  # verified, not approved yet
        admin = make_admin()
        from .services import approve_teacher

        approve_teacher(teacher, admin)
        self.client.logout()
        self.assertRedirects(login(), reverse("dashboards:home"), fetch_redirect_response=False)

    def test_approved_but_unverified_teacher_still_cannot_log_in(self):
        teacher = make_teacher("t2@example.com", verified=False)
        response = self.client.post(reverse("accounts:login"), {"email": "t2@example.com", "password": PASSWORD})
        self.assertContains(response, "verify your e-mail")
        self.assertFalse(teacher.is_active)

    def test_existing_session_ends_for_unverified_user(self):
        user = make_student("s@example.com", verified=False)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("dashboards:student")).status_code, 302)

    def test_verified_flag_default_for_superuser(self):
        self.assertTrue(make_admin().email_verified)


class PublicIdTests(TestCase):
    def test_student_gets_student_id_at_registration(self):
        student = make_student("a@example.com")
        self.assertRegex(student.public_id, r"^STU-\d{6}$")

    def test_ids_are_unique_and_sequential(self):
        ids = [make_student(f"s{i}@example.com").public_id for i in range(5)]
        self.assertEqual(len(set(ids)), 5)
        self.assertEqual(ids, sorted(ids))

    def test_teacher_id_is_assigned_on_approval_not_before(self):
        pending = make_teacher("t@example.com", approved=False)
        self.assertIsNone(pending.public_id)
        from .services import approve_teacher

        approve_teacher(pending, make_admin())
        pending.refresh_from_db()
        self.assertRegex(pending.public_id, r"^TCH-\d{6}$")

    def test_teacher_and_student_counters_are_independent(self):
        self.assertEqual(make_student("s@example.com").public_id, "STU-000001")
        self.assertEqual(make_teacher("t@example.com").public_id, "TCH-000001")

    def test_id_is_not_changed_by_ensure_or_profile_edit(self):
        student = make_student("s@example.com")
        first = student.public_id
        ensure_public_id(student)
        student.name = "New Name"
        student.save()
        student.refresh_from_db()
        self.assertEqual(student.public_id, first)

    def test_database_rejects_duplicate_ids(self):
        make_student("a@example.com")
        other = make_student("b@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=other.pk).update(public_id="STU-000001")

    def test_database_rejects_id_with_wrong_prefix_for_role(self):
        student = make_student("a@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=student.pk).update(public_id="TCH-000009")

    def test_collision_is_retried_with_next_number(self):
        make_student("a@example.com")  # STU-000001
        other = User.objects.create_user("b@example.com", "B", "Passw0rd123", email_verified=True)
        User.objects.filter(pk=other.pk).update(public_id=None)
        other.refresh_from_db()
        with mock.patch("accounts.identifiers._next_number", side_effect=[1, 2]):
            ensure_public_id(other)
        self.assertEqual(other.public_id, "STU-000002")

    def test_admin_has_no_id(self):
        self.assertIsNone(make_admin().public_id)

    def test_id_is_visible_on_profile_and_dashboard(self):
        student = make_student("a@example.com")
        self.client.force_login(student)
        self.assertContains(self.client.get(reverse("accounts:profile")), student.public_id)
        self.assertContains(self.client.get(reverse("dashboards:student")), student.public_id)
        teacher = make_teacher("t@example.com")
        self.client.force_login(teacher)
        self.assertContains(self.client.get(reverse("dashboards:teacher")), teacher.public_id)


class VerifyUserCommandTests(TestCase):
    def test_command_verifies_an_account(self):
        user = make_student("v@example.com", verified=False)
        call_command("verify_user", "V@Example.com")
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertTrue(user.is_active)

    def test_command_rejects_unknown_address(self):
        with self.assertRaises(CommandError):
            call_command("verify_user", "nobody@example.com")
