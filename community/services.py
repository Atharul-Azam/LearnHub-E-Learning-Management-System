"""Membership rules and notifications for announcements and discussion."""
from django.urls import reverse

from notifications.models import Notification
from notifications.services import notify

from courses.models import Enrollment


def is_member(user, course):
    """Course members: its teacher, and students enrolled in a *published* course."""
    if user.is_teacher:
        return course.teacher_id == user.pk
    if user.is_student:
        return course.is_published and Enrollment.objects.filter(student=user, course=course).exists()
    return False


def can_moderate(user, course):
    return user.is_admin or (user.is_teacher and course.teacher_id == user.pk)


def can_edit_post(user, post):
    return post.author_id is not None and post.author_id == user.pk


def course_url(user_is_teacher, course):
    name = "community:teacher_course" if user_is_teacher else "community:student_course"
    return reverse(name, args=[course.pk])


def notify_announcement(announcement):
    course = announcement.course
    for enrollment in Enrollment.objects.filter(course=course).select_related("student"):
        notify(
            enrollment.student,
            Notification.Category.DISCUSSION,
            f"New announcement in '{course.title}': {announcement.title}",
            course_url(False, course),
            f"announcement:{announcement.pk}",
        )


def notify_post(post):
    """Question -> the teacher; reply -> the question's author and the teacher (never the writer)."""
    course = post.course
    teacher = course.teacher
    author = post.author
    if post.is_question:
        if author and author.pk != teacher.pk:
            notify(
                teacher,
                Notification.Category.DISCUSSION,
                f"{author.name} asked a question in '{course.title}'.",
                course_url(True, course),
                f"post:{post.pk}:teacher",
            )
        return
    question = post.parent
    who = author.name if author else "Someone"
    if question.author and question.author_id != (author.pk if author else None):
        notify(
            question.author,
            Notification.Category.DISCUSSION,
            f"{who} replied to your question in '{course.title}'.",
            course_url(question.author.is_teacher, course),
            f"post:{post.pk}:asker",
        )
    if author is None or author.pk != teacher.pk:
        if question.author_id != teacher.pk:
            notify(
                teacher,
                Notification.Category.DISCUSSION,
                f"New reply in the discussion of '{course.title}'.",
                course_url(True, course),
                f"post:{post.pk}:teacher",
            )
