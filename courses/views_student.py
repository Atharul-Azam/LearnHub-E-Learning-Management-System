"""Student views: UC13 browse/search, UC14 enroll, enrolled-course list and course page."""
from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from assignments.models import Submission
from core.decorators import login_required_any, student_required
from core.pagination import paginate
from core.services import BusinessRuleError
from progress.services import viewed_material_ids

from . import private, services
from .access import get_student_enrollment
from .models import Course, CourseAccessRequest, Enrollment, Favourite


def _share_url(request, course):
    """Public courses share their detail page. Private courses never expose a content link."""
    if course.is_private:
        return ""
    return request.build_absolute_uri(reverse("courses:detail", args=[course.pk]))


@student_required
def browse(request):
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    sort = request.GET.get("sort", "newest")
    courses = services.search_courses(services.published_courses(), q, category)
    courses = courses.order_by("created_at", "id") if sort == "oldest" else courses.order_by("-created_at", "-id")
    enrolled_ids = set(Enrollment.objects.filter(student=request.user).values_list("course_id", flat=True))
    favourite_ids = set(Favourite.objects.filter(student=request.user).values_list("course_id", flat=True))
    page, qs = paginate(request, courses.annotate(student_total=Count("enrollments", distinct=True)))
    return render(
        request,
        "courses/browse.html",
        {
            "page": page,
            "querystring": qs,
            "q": q,
            "category": category,
            "sort": "oldest" if sort == "oldest" else "newest",
            "categories": list(services.published_categories()),
            "enrolled_ids": enrolled_ids,
            "favourite_ids": favourite_ids,
            "searching": bool(q or category),
        },
    )


@student_required
def detail(request, pk):
    """Public published courses are open to every student; a private course only to its members."""
    course = get_object_or_404(Course.objects.select_related("teacher"), pk=pk, visibility=Course.Visibility.PUBLISHED)
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()
    if course.is_private and not enrolled:
        raise Http404  # existence of a private course is not disclosed
    return render(
        request,
        "courses/detail.html",
        {
            "course": course,
            "enrolled": enrolled,
            "is_favourite": Favourite.objects.filter(student=request.user, course=course).exists(),
            "share_url": _share_url(request, course),
            "student_total": course.enrollments.count(),
            "materials": course.materials.order_by("created_at", "id").values_list("title", flat=True),
            "assignments": course.assignments.order_by("deadline", "id").values_list("title", flat=True),
        },
    )


@student_required
@require_POST
def enroll(request, pk):
    course = get_object_or_404(Course, pk=pk, visibility=Course.Visibility.PUBLISHED)
    if course.is_private:
        raise Http404
    try:
        created = services.enroll_student(request.user, course)
    except BusinessRuleError as exc:
        messages.error(request, str(exc))
        return redirect("courses:browse")
    if created:
        messages.success(request, f"You are now enrolled in '{course.title}'.")
    else:
        messages.info(request, "You are already enrolled in this course.")
    return redirect("courses:detail", pk=pk)


# ---------------------------------------------------------------- favourites
@student_required
@require_POST
def favourite_toggle(request, pk):
    """Save / unsave a course the student can legitimately see."""
    course = get_object_or_404(Course, pk=pk, visibility=Course.Visibility.PUBLISHED)
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()
    if course.is_private and not enrolled:
        raise Http404
    existing = Favourite.objects.filter(student=request.user, course=course)
    if existing.exists():
        existing.delete()
        messages.info(request, f"'{course.title}' was removed from your favourites.")
    else:
        try:
            Favourite.objects.create(student=request.user, course=course)
        except IntegrityError:  # double click; the unique constraint prevents duplicates
            pass
        else:
            messages.success(request, f"'{course.title}' was added to your favourites.")
    target = request.POST.get("next", "")
    if target.startswith("/") and not target.startswith("//"):
        return redirect(target)
    return redirect("courses:detail", pk=pk)


@student_required
def favourites(request):
    items = (
        Favourite.objects.filter(student=request.user, course__visibility=Course.Visibility.PUBLISHED)
        .select_related("course", "course__teacher")
        .order_by("-created_at", "-id")
    )
    enrolled_ids = set(Enrollment.objects.filter(student=request.user).values_list("course_id", flat=True))
    # A private course the student lost access to must not stay visible through a favourite.
    visible = [f for f in items if not f.course.is_private or f.course_id in enrolled_ids]
    for f in visible:
        f.share_url = _share_url(request, f.course)  # empty for private courses: they are never shared by link
    page, qs = paginate(request, visible)
    return render(
        request,
        "courses/favourites.html",
        {"page": page, "querystring": qs, "enrolled_ids": enrolled_ids, "favourite_ids": {f.course_id for f in visible}},
    )


# -------------------------------------------------- private course invitations
@student_required
def join(request, token):
    """Landing page of an invitation link: basic information and a request button, never content."""
    course, problem = private.resolve_invite(token)
    if course is None:
        return render(request, "courses/join_invalid.html", {"expired": problem == private.EXPIRED}, status=404)
    if Enrollment.objects.filter(student=request.user, course=course).exists():
        return redirect("courses:open_course", pk=course.pk)
    access = CourseAccessRequest.objects.filter(student=request.user, course=course).first()
    if request.method == "POST":
        try:
            private.request_access(request.user, course)
        except BusinessRuleError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Your access request was sent. You will be notified when the teacher decides.")
        return redirect("courses:join", token=token)
    return render(request, "courses/join.html", {"course": course, "access": access, "token": token})


@student_required
def my_courses(request):
    enrollments = (
        Enrollment.objects.filter(student=request.user, course__visibility=Course.Visibility.PUBLISHED)
        .select_related("course", "course__teacher")
        .order_by("-enrolled_at", "-id")
    )
    page, qs = paginate(request, enrollments)
    return render(request, "courses/my_courses.html", {"page": page, "querystring": qs})


@student_required
def open_course(request, pk):
    enrollment = get_student_enrollment(request.user, pk)
    Enrollment.objects.filter(pk=enrollment.pk).update(last_accessed_at=timezone.now())
    course = enrollment.course
    materials = list(course.materials.order_by("created_at", "id"))
    viewed = viewed_material_ids(request.user, course)
    submissions = {s.assignment_id: s for s in Submission.objects.filter(student=request.user, assignment__course=course)}
    assignments = list(course.assignments.order_by("deadline", "id"))
    for assignment in assignments:
        assignment.my_submission = submissions.get(assignment.pk)
    for material in materials:
        material.viewed = material.pk in viewed
    return render(
        request,
        "courses/open_course.html",
        {
            "course": course,
            "enrollment": enrollment,
            "materials": materials,
            "assignments": assignments,
            "share_url": _share_url(request, course),
        },
    )


@login_required_any
def thumbnail(request, pk):
    """Serve a course thumbnail.

    Public published course: any signed-in user. Hidden course: administrator or owner.
    Private course: administrator, owner or an enrolled student only.
    """
    from core.files import file_response

    course = get_object_or_404(Course, pk=pk)
    user = request.user
    privileged = user.is_admin or course.teacher_id == user.pk
    if not privileged:
        if not course.is_published:
            raise Http404
        if course.is_private and not Enrollment.objects.filter(student=user, course=course).exists():
            raise Http404
    if not course.thumbnail:
        raise Http404
    return file_response(course.thumbnail, course.thumbnail.name)
