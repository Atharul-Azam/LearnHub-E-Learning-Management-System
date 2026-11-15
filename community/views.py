"""Course announcements and discussion (Q&A)."""
import logging

from django.contrib import messages
from django.db import DatabaseError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import login_required_any, student_required, teacher_required
from core.pagination import paginate
from core.views import confirm_page
from courses.access import get_student_enrollment
from courses.services import get_owned_course_or_404

from . import services
from .forms import AnnouncementForm, PostForm
from .models import Announcement, Post

logger = logging.getLogger("learnhub")


def _course_for_member(user, pk):
    """The course if ``user`` is its teacher or an enrolled student; 404/403 otherwise."""
    if user.is_teacher:
        return get_owned_course_or_404(user, pk)
    if user.is_student:
        return get_student_enrollment(user, pk).course
    raise Http404


def _course_page(request, course, *, edit_post=None, post_form=None):
    questions = course.posts.filter(parent__isnull=True).select_related("author").prefetch_related("replies__author")
    page, qs = paginate(request, questions.order_by("-created_at", "-id"), per_page=10)
    return render(
        request,
        "community/course.html",
        {
            "course": course,
            "is_teacher": request.user.is_teacher,
            "announcements": course.announcements.all()[:10],
            "announcement_form": AnnouncementForm() if request.user.is_teacher else None,
            "post_form": post_form or PostForm(),
            "page": page,
            "querystring": qs,
            "can_moderate": services.can_moderate(request.user, course),
        },
    )


@teacher_required
def teacher_course(request, pk):
    return _course_page(request, _course_for_member(request.user, pk))


@student_required
def student_course(request, pk):
    return _course_page(request, _course_for_member(request.user, pk))


@login_required_any
@require_POST
def post_create(request, pk):
    course = _course_for_member(request.user, pk)
    form = PostForm(request.POST)
    parent = None
    parent_id = request.POST.get("parent", "")
    if parent_id:
        parent = Post.objects.filter(pk=parent_id if parent_id.isdigit() else 0, course=course).first()
        if parent is None:
            raise Http404
        if parent.parent_id is not None:  # replies always attach to the top-level question
            parent = parent.parent
    if form.is_valid():
        try:
            post = Post.objects.create(course=course, author=request.user, parent=parent, body=form.cleaned_data["body"])
        except DatabaseError:
            logger.exception("Post creation failed")
            messages.error(request, "Your message could not be saved. Please try again.")
        else:
            services.notify_post(post)
            messages.success(request, "Your reply was posted." if parent else "Your question was posted.")
    else:
        messages.error(request, "Your message was not posted: " + " ".join(form.errors.get("body", ["invalid"])))
    return redirect(services.course_url(request.user.is_teacher, course))


def _post_for_user(user, pk):
    """A post the user may at least see: members of its course, or an administrator."""
    post = get_object_or_404(Post.objects.select_related("course", "author", "parent"), pk=pk)
    if not (user.is_admin or services.is_member(user, post.course)):
        raise Http404
    return post


@login_required_any
def post_edit(request, pk):
    post = _post_for_user(request.user, pk)
    if not services.can_edit_post(request.user, post):  # only the author edits
        raise Http404
    form = PostForm(request.POST or None, instance=post)
    if request.method == "POST" and form.is_valid():
        post = form.save(commit=False)
        post.edited_at = timezone.now()
        post.save(update_fields=["body", "edited_at"])
        messages.success(request, "Your message was updated.")
        return redirect(services.course_url(request.user.is_teacher, post.course))
    return render(request, "community/post_edit.html", {"form": form, "post": post, "course": post.course})


@login_required_any
def post_delete(request, pk):
    post = _post_for_user(request.user, pk)
    allowed = services.can_edit_post(request.user, post) or services.can_moderate(request.user, post.course)
    if not allowed:
        raise Http404
    back = reverse("dashboards:home") if request.user.is_admin else services.course_url(request.user.is_teacher, post.course)
    if request.method == "POST":
        post.delete()  # replies go with a question (CASCADE)
        messages.success(request, "The message was deleted.")
        return redirect(back)
    extra = " Its replies will be deleted as well." if post.is_question else ""
    return confirm_page(
        request,
        title="Delete message",
        message="Delete this message?" + extra,
        confirm_label="Delete",
        cancel_url=back,
        danger=True,
    )


# ------------------------------------------------------------- announcements
@teacher_required
@require_POST
def announcement_create(request, pk):
    course = get_owned_course_or_404(request.user, pk)
    form = AnnouncementForm(request.POST)
    if form.is_valid():
        announcement = form.save(commit=False)
        announcement.course = course
        announcement.author = request.user
        announcement.save()
        services.notify_announcement(announcement)
        messages.success(request, "The announcement was published to the enrolled students.")
    else:
        messages.error(request, "The announcement was not published: title and text are required.")
    return redirect("community:teacher_course", pk=pk)


@teacher_required
def announcement_delete(request, pk):
    announcement = get_object_or_404(Announcement.objects.select_related("course"), pk=pk, course__teacher=request.user)
    back = reverse("community:teacher_course", args=[announcement.course_id])
    if request.method == "POST":
        announcement.delete()
        messages.success(request, "The announcement was deleted.")
        return redirect(back)
    return confirm_page(
        request,
        title="Delete announcement",
        message=f"Delete the announcement '{announcement.title}'?",
        confirm_label="Delete",
        cancel_url=back,
        danger=True,
    )
