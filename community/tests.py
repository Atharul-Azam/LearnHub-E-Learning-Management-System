from django.urls import reverse

from core.factories import MediaTestCase, enroll, make_admin, make_course, make_student, make_teacher
from notifications.models import Notification

from .models import Announcement, Post


class CommunityBase(MediaTestCase):
    def setUp(self):
        self.teacher = make_teacher("t@example.com", name="Tina")
        self.other_teacher = make_teacher("t2@example.com")
        self.student = make_student("s@example.com", name="Sam")
        self.mate = make_student("m@example.com", name="Mia")
        self.outsider = make_student("o@example.com", name="Olga")
        self.admin = make_admin()
        self.course = make_course(self.teacher)
        self.private = make_course(self.teacher, "Hidden gem", access="private")
        for s in (self.student, self.mate):
            enroll(s, self.course)
        enroll(self.student, self.private)
        self.url = reverse("community:student_course", args=[self.course.pk])
        self.post_url = reverse("community:post_create", args=[self.course.pk])


class AccessTests(CommunityBase):
    def test_enrolled_student_and_owner_teacher_can_open(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("community:teacher_course", args=[self.course.pk])).status_code, 200)

    def test_outsiders_cannot_read_or_post(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.post_url, {"body": "hi"}).status_code, 403)
        self.assertEqual(Post.objects.count(), 0)

    def test_other_teacher_cannot_access(self):
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(reverse("community:teacher_course", args=[self.course.pk])).status_code, 404)

    def test_private_course_discussion_hidden_from_non_members(self):
        self.client.force_login(self.outsider)
        url = reverse("community:student_course", args=[self.private.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(reverse("community:post_create", args=[self.private.pk]), {"body": "x"}).status_code, 404)

    def test_roles_use_their_own_page(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("community:teacher_course", args=[self.course.pk])).status_code, 403)

    def test_admin_has_no_member_view(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_anonymous_redirected(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)


class DiscussionTests(CommunityBase):
    def test_student_asks_and_teacher_is_notified(self):
        self.client.force_login(self.student)
        self.client.post(self.post_url, {"body": "How do loops work?"})
        post = Post.objects.get()
        self.assertIsNone(post.parent)
        self.assertEqual(post.author, self.student)
        self.assertTrue(Notification.objects.filter(recipient=self.teacher, message__contains="asked a question").exists())
        self.assertContains(self.client.get(self.url), "How do loops work?")

    def test_teacher_reply_notifies_student_and_shows_name_and_time(self):
        question = Post.objects.create(course=self.course, author=self.student, body="Q?")
        self.client.force_login(self.teacher)
        self.client.post(self.post_url, {"body": "Use for.", "parent": question.pk})
        reply = Post.objects.get(parent=question)
        self.assertEqual(reply.author, self.teacher)
        self.assertTrue(Notification.objects.filter(recipient=self.student, message__contains="replied").exists())
        response = self.client.get(reverse("community:teacher_course", args=[self.course.pk]))
        self.assertContains(response, "Tina")
        self.assertContains(response, "Use for.")

    def test_classmate_can_reply_and_nested_reply_attaches_to_question(self):
        question = Post.objects.create(course=self.course, author=self.student, body="Q?")
        reply = Post.objects.create(course=self.course, author=self.teacher, parent=question, body="A")
        self.client.force_login(self.mate)
        self.client.post(self.post_url, {"body": "Me too", "parent": reply.pk})
        self.assertEqual(Post.objects.get(body="Me too").parent, question)

    def test_cannot_reply_to_a_post_of_another_course(self):
        other_course = make_course(self.other_teacher, "Elsewhere")
        foreign = Post.objects.create(course=other_course, author=self.other_teacher, body="x")
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(self.post_url, {"body": "y", "parent": foreign.pk}).status_code, 404)

    def test_empty_message_rejected(self):
        self.client.force_login(self.student)
        self.client.post(self.post_url, {"body": "   "})
        self.assertEqual(Post.objects.count(), 0)

    def test_html_is_escaped(self):
        Post.objects.create(course=self.course, author=self.student, body="<script>alert(1)</script>")
        self.client.force_login(self.mate)
        response = self.client.get(self.url)
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")


class EditDeleteTests(CommunityBase):
    def setUp(self):
        super().setUp()
        self.question = Post.objects.create(course=self.course, author=self.student, body="Original")
        self.reply = Post.objects.create(course=self.course, author=self.teacher, parent=self.question, body="Answer")

    def test_author_can_edit_and_it_is_marked_edited(self):
        self.client.force_login(self.student)
        self.client.post(reverse("community:post_edit", args=[self.question.pk]), {"body": "Changed"})
        self.question.refresh_from_db()
        self.assertEqual(self.question.body, "Changed")
        self.assertIsNotNone(self.question.edited_at)

    def test_others_cannot_edit_even_teacher_or_admin(self):
        for user in (self.mate, self.teacher, self.admin, self.outsider):
            self.client.force_login(user)
            self.client.post(reverse("community:post_edit", args=[self.question.pk]), {"body": "Hacked"})
        self.question.refresh_from_db()
        self.assertEqual(self.question.body, "Original")

    def test_author_can_delete_own_post(self):
        self.client.force_login(self.student)
        url = reverse("community:post_delete", args=[self.question.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(Post.objects.filter(pk=self.question.pk).exists())
        self.client.post(url)
        self.assertFalse(Post.objects.filter(pk=self.question.pk).exists())
        self.assertFalse(Post.objects.filter(pk=self.reply.pk).exists())  # replies go with the question

    def test_teacher_can_moderate_own_course(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse("community:post_delete", args=[self.question.pk]))
        self.assertFalse(Post.objects.filter(pk=self.question.pk).exists())

    def test_other_teacher_and_classmate_cannot_delete(self):
        for user in (self.other_teacher, self.mate, self.outsider):
            self.client.force_login(user)
            self.client.post(reverse("community:post_delete", args=[self.question.pk]))
        self.assertTrue(Post.objects.filter(pk=self.question.pk).exists())

    def test_admin_can_moderate_anywhere(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("community:post_delete", args=[self.reply.pk]))
        self.assertFalse(Post.objects.filter(pk=self.reply.pk).exists())

    def test_admin_interface_has_no_discussion_section(self):
        from django.urls import NoReverseMatch

        with self.assertRaises(NoReverseMatch):
            reverse("community:admin_list")
        self.client.force_login(self.admin)
        for name in ("dashboards:admin", "accounts:user_list", "courses:admin_list"):
            self.assertNotContains(self.client.get(reverse(name)), "Discussions")

    def test_delete_does_nothing_on_get(self):
        self.client.force_login(self.teacher)
        self.client.get(reverse("community:post_delete", args=[self.question.pk]))
        self.assertTrue(Post.objects.filter(pk=self.question.pk).exists())


class AnnouncementTests(CommunityBase):
    def test_teacher_publishes_and_enrolled_students_are_notified(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse("community:announcement_create", args=[self.course.pk]), {"title": "Exam moved", "body": "Friday."})
        self.assertEqual(Announcement.objects.count(), 1)
        notified = set(Notification.objects.filter(message__contains="Exam moved").values_list("recipient_id", flat=True))
        self.assertEqual(notified, {self.student.pk, self.mate.pk})
        self.client.force_login(self.student)
        self.assertContains(self.client.get(self.url), "Exam moved")

    def test_students_cannot_publish(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(reverse("community:announcement_create", args=[self.course.pk]), {"title": "x", "body": "y"}).status_code, 403)

    def test_other_teacher_cannot_publish_or_delete(self):
        ann = Announcement.objects.create(course=self.course, author=self.teacher, title="T", body="B")
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.post(reverse("community:announcement_create", args=[self.course.pk]), {"title": "x", "body": "y"}).status_code, 404)
        self.client.post(reverse("community:announcement_delete", args=[ann.pk]))
        self.assertTrue(Announcement.objects.filter(pk=ann.pk).exists())

    def test_validation_and_owner_delete(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse("community:announcement_create", args=[self.course.pk]), {"title": "", "body": ""})
        self.assertEqual(Announcement.objects.count(), 0)
        ann = Announcement.objects.create(course=self.course, author=self.teacher, title="T", body="B")
        self.client.post(reverse("community:announcement_delete", args=[ann.pk]))
        self.assertEqual(Announcement.objects.count(), 0)

    def test_outsider_cannot_see_announcements(self):
        Announcement.objects.create(course=self.course, author=self.teacher, title="Secret news", body="B")
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get(self.url), "Secret news", status_code=403)
