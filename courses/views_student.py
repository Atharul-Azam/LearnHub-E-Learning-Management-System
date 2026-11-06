"""Student views: UC13 browse/search, UC14 enroll, enrolled-course list and course page."""
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from assignments.models import Submission
from core.decorators import login_required_any, student_required
from core.pagination import paginate
from core.services import BusinessRuleError
from progress.services import viewed_material_ids

from . import services
from .access import get_student_enrollment
from .models import Course, Enrollment


@student_required
def browse(request):
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    courses = services.search_courses(services.published_courses(), q, category).order_by("-created_at", "-id")
    enrolled_ids = set(Enrollment.objects.filter(student=request.user).values_list("course_id", flat=True))
    page, qs = paginate(request, courses)
    return render(
        request,
        "courses/browse.html",
        {
            "page": page,
            "querystring": qs,
            "q": q,
            "category": category,
            "categories": list(services.published_categories()),
            "enrolled_ids": enrolled_ids,
            "searching": bool(q or category),
        },
    )


@student_required
def detail(request, pk):
    course = get_object_or_404(services.published_courses(), pk=pk)
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()
    return render(
        request,
        "courses/detail.html",
        {
            "course": course,
            "enrolled": enrolled,
            "materials": course.materials.order_by("created_at", "id").values_list("title", flat=True),
            "assignments": course.assignments.order_by("deadline", "id").values_list("title", flat=True),
        },
    )


@student_required
@require_POST
def enroll(request, pk):
    course = get_object_or_404(Course, pk=pk)
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
        {"course": course, "enrollment": enrollment, "materials": materials, "assignments": assignments},
    )


@login_required_any
def thumbnail(request, pk):
    """Serve a course thumbnail. Published: any logged-in user. Hidden: admin or owner only."""
    from core.files import file_response

    course = get_object_or_404(Course, pk=pk)
    user = request.user
    if not course.is_published and not (user.is_admin or course.teacher_id == user.pk):
        raise Http404
    if not course.thumbnail:
        raise Http404
    return file_response(course.thumbnail, course.thumbnail.name)
