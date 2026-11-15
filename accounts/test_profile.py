"""Profile, settings, appearance persistence, security and account deletion."""
from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import Client, override_settings
from django.urls import reverse

from assignments.models import Submission
from core.factories import (
    PASSWORD,
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
    png_file,
)

from .models import User


class ProfileTests(MediaTestCase):
    def setUp(self):
        self.student = make_student("s@example.com", name="Sam")
        self.teacher = make_teacher("t@example.com", name="Tina")
        self.client.force_login(self.student)

    def test_profile_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 302)

    def test_student_profile_shows_real_figures(self):
        c1 = make_course(self.teacher, "One")
        c2 = make_course(self.teacher, "Two")
        e1 = enroll(self.student, c1)
        enroll(self.student, c2)
        type(e1).objects.filter(pk=e1.pk).update(progress=100)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.context["enrolled_total"], 2)
        self.assertEqual(response.context["completed_total"], 1)
        self.assertEqual(response.context["overall_progress"], 50)
        self.assertContains(response, self.student.email)

    def test_teacher_profile_counts_courses_and_students(self):
        self.client.force_login(self.teacher)
        course = make_course(self.teacher)
        enroll(self.student, course)
        enroll(make_student("s2@example.com"), course)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.context["courses_created"], 1)
        self.assertEqual(response.context["students_total"], 2)

    def test_edit_name_and_teacher_bio(self):
        self.client.post(reverse("accounts:settings_profile"), {"name": "  Samuel   Lee "})
        self.student.refresh_from_db()
        self.assertEqual(self.student.name, "Samuel Lee")
        self.client.force_login(self.teacher)
        self.client.post(reverse("accounts:settings_profile"), {"name": "Tina", "bio": "Hello", "expertise": "Python"})
        self.teacher.refresh_from_db()
        self.assertEqual((self.teacher.bio, self.teacher.expertise), ("Hello", "Python"))

    def test_student_cannot_set_teacher_fields(self):
        self.client.post(reverse("accounts:settings_profile"), {"name": "Sam", "bio": "x", "expertise": "y"})
        self.student.refresh_from_db()
        self.assertEqual((self.student.bio, self.student.expertise), ("", ""))

    def test_name_is_required_and_public_id_cannot_be_posted(self):
        original = self.student.public_id
        response = self.client.post(reverse("accounts:settings_profile"), {"name": "", "public_id": "STU-999999"})
        self.assertEqual(response.status_code, 200)
        self.client.post(reverse("accounts:settings_profile"), {"name": "Sam", "public_id": "STU-999999"})
        self.student.refresh_from_db()
        self.assertEqual(self.student.public_id, original)

    def test_upload_valid_profile_picture_and_serve_it(self):
        self.client.post(reverse("accounts:settings_profile"), {"name": "Sam", "profile_picture": png_file("me.png")})
        self.student.refresh_from_db()
        self.assertTrue(self.student.profile_picture)
        self.assertRegex(self.student.profile_picture.name, r"^avatars/[0-9a-f]{32}\.png$")
        response = self.client.get(reverse("accounts:avatar", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_avatar_requires_login_and_missing_is_404(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounts:avatar", args=[self.student.pk])).status_code, 302)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("accounts:avatar", args=[self.student.pk])).status_code, 404)

    def test_unsafe_profile_pictures_are_rejected(self):
        for upload in (fake_file("evil.png"), fake_file("evil.exe"), fake_file("evil.php"), pdf_file("doc.png")):
            response = self.client.post(reverse("accounts:settings_profile"), {"name": "Sam", "profile_picture": upload})
            self.assertEqual(response.status_code, 200, upload.name)
        self.student.refresh_from_db()
        self.assertFalse(self.student.profile_picture)

    def test_oversized_picture_is_rejected(self):
        rules = {"avatar": {"extensions": {"png"}, "max_bytes": 10}}
        with override_settings(UPLOAD_RULES={**settings.UPLOAD_RULES, **rules}):
            response = self.client.post(reverse("accounts:settings_profile"), {"name": "Sam", "profile_picture": png_file()})
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertFalse(self.student.profile_picture)

    def test_replacing_picture_deletes_the_old_file(self):
        import os

        self.client.post(reverse("accounts:settings_profile"), {"name": "Sam", "profile_picture": png_file("a.png")})
        self.student.refresh_from_db()
        old_path = self.student.profile_picture.path
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("accounts:settings_profile"), {"name": "Sam", "profile_picture": png_file("b.png")})
        self.assertFalse(os.path.exists(old_path))

    def test_remove_picture_returns_to_default(self):
        self.client.post(reverse("accounts:settings_profile"), {"name": "Sam", "profile_picture": png_file()})
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("accounts:settings_profile"), {"name": "Sam", "remove_picture": "on"})
        self.student.refresh_from_db()
        self.assertFalse(self.student.profile_picture)

    def test_user_cannot_edit_somebody_elses_profile_by_posting_an_id(self):
        self.client.post(reverse("accounts:settings_profile"), {"name": "Hacked", "id": self.teacher.pk, "pk": self.teacher.pk})
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.name, "Tina")


class SettingsTests(MediaTestCase):
    def setUp(self):
        self.student = make_student("s@example.com")
        self.client.force_login(self.student)

    def test_every_settings_page_loads(self):
        for name in ("settings", "settings_profile", "settings_password", "settings_notifications",
                     "settings_appearance", "settings_security", "settings_delete"):
            self.assertEqual(self.client.get(reverse(f"accounts:{name}")).status_code, 200, name)

    def test_settings_require_login(self):
        self.client.logout()
        for name in ("settings", "settings_appearance", "settings_delete"):
            self.assertEqual(self.client.get(reverse(f"accounts:{name}")).status_code, 302, name)

    def test_theme_and_font_persist_across_logout_and_login(self):
        self.client.post(reverse("accounts:settings_appearance"), {"theme": "dark", "font": "serif"})
        self.client.post(reverse("accounts:logout"))
        self.client.post(reverse("accounts:login"), {"email": "s@example.com", "password": PASSWORD})
        response = self.client.get(reverse("dashboards:student"))
        self.assertContains(response, 'data-theme="dark"')
        self.assertContains(response, 'data-font="serif"')

    def test_invalid_theme_is_rejected(self):
        response = self.client.post(reverse("accounts:settings_appearance"), {"theme": "neon", "font": "sans"})
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.theme, "system")

    def test_default_theme_is_system(self):
        self.assertContains(self.client.get(reverse("dashboards:student")), 'data-theme="system"')

    def test_notification_preferences_are_saved(self):
        self.client.post(reverse("accounts:settings_notifications"), {"notify_courses": "on"})
        self.student.refresh_from_db()
        self.assertEqual((self.student.notify_courses, self.student.notify_assignments, self.student.notify_discussion), (True, False, False))

    def test_logout_is_post_only_and_works(self):
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_settings_page_offers_logout(self):
        self.assertContains(self.client.get(reverse("accounts:settings")), reverse("accounts:logout"))

    def test_change_password_requires_old_password_and_rules(self):
        url = reverse("accounts:settings_password")
        bad_old = self.client.post(url, {"old_password": "nope", "new_password1": "NewPass123", "new_password2": "NewPass123"})
        self.assertEqual(bad_old.status_code, 200)
        weak = self.client.post(url, {"old_password": PASSWORD, "new_password1": "short", "new_password2": "short"})
        self.assertEqual(weak.status_code, 200)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(PASSWORD))

    def test_change_password_keeps_this_session_and_ends_others(self):
        other = Client()
        other.force_login(self.student)
        response = self.client.post(
            reverse("accounts:settings_password"),
            {"old_password": PASSWORD, "new_password1": "NewPass123", "new_password2": "NewPass123"},
        )
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("NewPass123"))
        self.assertEqual(self.client.get(reverse("dashboards:student")).status_code, 200)
        self.assertEqual(other.get(reverse("dashboards:student")).status_code, 302)

    def test_sign_out_other_devices(self):
        other = Client()
        other.force_login(self.student)
        self.client.post(reverse("accounts:sign_out_others"))
        self.assertEqual(self.client.get(reverse("dashboards:student")).status_code, 200)
        self.assertEqual(other.get(reverse("dashboards:student")).status_code, 302)
        self.assertEqual(self.client.get(reverse("accounts:sign_out_others")).status_code, 405)


class AccountDeletionTests(MediaTestCase):
    def setUp(self):
        self.student = make_student("s@example.com")
        self.teacher = make_teacher("t@example.com")
        self.client.force_login(self.student)
        self.url = reverse("accounts:settings_delete")

    def test_warning_is_shown(self):
        self.assertContains(self.client.get(self.url), "permanently deletes your account")

    def test_wrong_password_does_not_delete(self):
        self.client.post(self.url, {"password": "WrongPass1", "understand": "on"})
        self.assertTrue(User.objects.filter(pk=self.student.pk).exists())

    def test_confirmation_checkbox_is_required(self):
        self.client.post(self.url, {"password": PASSWORD})
        self.assertTrue(User.objects.filter(pk=self.student.pk).exists())

    def test_student_deletion_removes_own_data_and_sessions(self):
        course = make_course(self.teacher)
        enroll(self.student, course)
        submission = make_submission(make_assignment(course), self.student)
        other = Client()
        other.force_login(self.student)
        response = self.client.post(self.url, {"password": PASSWORD, "understand": "on"}, follow=True)
        self.assertContains(response, "permanently deleted")
        self.assertFalse(User.objects.filter(pk=self.student.pk).exists())
        self.assertFalse(Submission.objects.filter(pk=submission.pk).exists())
        self.assertEqual(other.get(reverse("dashboards:student")).status_code, 302)
        self.assertEqual(Session.objects.filter(session_key=other.session.session_key).count(), 0)

    def test_deleting_a_student_does_not_touch_other_users_or_the_course(self):
        course = make_course(self.teacher)
        mate = make_student("m@example.com")
        enroll(mate, course)
        enroll(self.student, course)
        self.client.post(self.url, {"password": PASSWORD, "understand": "on"})
        self.assertEqual(course.enrollments.count(), 1)
        self.assertTrue(User.objects.filter(pk=mate.pk).exists())

    def test_teacher_with_courses_cannot_delete(self):
        make_course(self.teacher)
        self.client.force_login(self.teacher)
        self.client.post(self.url, {"password": PASSWORD, "understand": "on"})
        self.assertTrue(User.objects.filter(pk=self.teacher.pk).exists())

    def test_teacher_without_courses_can_delete(self):
        self.client.force_login(self.teacher)
        self.client.post(self.url, {"password": PASSWORD, "understand": "on"})
        self.assertFalse(User.objects.filter(pk=self.teacher.pk).exists())

    def test_admin_cannot_self_delete(self):
        admin = make_admin()
        self.client.force_login(admin)
        self.client.post(self.url, {"password": PASSWORD, "understand": "on"})
        self.assertTrue(User.objects.filter(pk=admin.pk).exists())

    def test_deletion_only_affects_the_requesting_user(self):
        self.client.post(self.url, {"password": PASSWORD, "understand": "on", "id": self.teacher.pk, "pk": self.teacher.pk})
        self.assertTrue(User.objects.filter(pk=self.teacher.pk).exists())

    def test_delete_is_not_possible_with_get(self):
        self.client.get(self.url + "?password=x&understand=on")
        self.assertTrue(User.objects.filter(pk=self.student.pk).exists())

    def test_discussion_posts_survive_author_deletion(self):
        from community.models import Post

        course = make_course(self.teacher)
        enroll(self.student, course)
        post = Post.objects.create(course=course, author=self.student, body="Question?")
        self.client.post(self.url, {"password": PASSWORD, "understand": "on"})
        post.refresh_from_db()
        self.assertIsNone(post.author)
