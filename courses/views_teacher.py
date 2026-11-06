"""Teacher views: UC7 create, UC8 edit/delete, UC11 enrolled students."""
import logging

from django.contrib import messages
from django.db import DatabaseError
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse

from core.decorators import teacher_required
from core.pagination import paginate
from core.views import confirm_page

from . import services
from .forms import CourseForm
from .models import Course, Enrollment

logger = logging.getLogger("learnhub")


def _category_options():
    return list(Course.objects.exclude(category="").order_by("category").values_list("category", flat=True).distinct())


@teacher_required
def teacher_list(request):
    courses = (
        Course.objects.filter(teacher=request.user)
        .annotate(
            enrollment_total=Count("enrollments", distinct=True),
            material_total=Count("materials", distinct=True),
            assignment_total=Count("assignments", distinct=True),
        )
        .order_by("-created_at", "-id")
    )
    page, qs = paginate(request, courses)
    return render(request, "teacher/course_list.html", {"page": page, "querystring": qs})


@teacher_required
def teacher_create(request):
    form = CourseForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            form.instance.teacher = request.user
            course = form.save()
        except DatabaseError:
            logger.exception("Course creation failed")
            messages.error(request, "The course could not be saved. Please try again.")
        else:
            messages.success(request, f"Course '{course.title}' was created and is published.")
            return redirect("courses:teacher_detail", pk=course.pk)
    elif request.method == "POST":
        messages.error(request, "Please correct the errors below.")
    return render(request, "teacher/course_form.html", {"form": form, "categories": _category_options(), "editing": False})


@teacher_required
def teacher_detail(request, pk):
    course = services.get_owned_course_or_404(request.user, pk)
    materials = course.materials.order_by("created_at", "id")
    assignments = course.assignments.annotate(submission_total=Count("submissions")).order_by("deadline", "id")
    return render(
        request,
        "teacher/course_detail.html",
        {
            "course": course,
            "materials": materials,
            "assignments": assignments,
            "enrollment_total": course.enrollments.count(),
        },
    )


@teacher_required
def teacher_edit(request, pk):
    course = services.get_owned_course_or_404(request.user, pk)
    form = CourseForm(request.POST or None, request.FILES or None, instance=course)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except DatabaseError:
            logger.exception("Course update failed")
            messages.error(request, "The changes could not be saved. Please try again.")
        else:
            messages.success(request, "The course was updated.")
            return redirect("courses:teacher_detail", pk=course.pk)
    elif request.method == "POST":
        messages.error(request, "Please correct the errors below.")
    return render(
        request,
        "teacher/course_form.html",
        {"form": form, "course": course, "categories": _category_options(), "editing": True},
    )


@teacher_required
def teacher_delete(request, pk):
    course = services.get_owned_course_or_404(request.user, pk)
    if request.method == "POST":
        title = course.title
        try:
            services.remove_course(course)
        except DatabaseError:
            logger.exception("Course deletion failed")
            messages.error(request, "The course could not be deleted. Please try again.")
            return redirect("courses:teacher_detail", pk=pk)
        messages.success(request, f"Course '{title}' was deleted.")
        return redirect("courses:teacher_list")
    return confirm_page(
        request,
        title="Delete course",
        message=f"Delete the course '{course.title}'? Its materials, assignments, enrollments and "
        "student submissions will be permanently deleted. This cannot be undone.",
        confirm_label="Delete course",
        cancel_url=reverse("courses:teacher_detail", args=[pk]),
        danger=True,
    )


@teacher_required
def teacher_students(request, pk):
    course = services.get_owned_course_or_404(request.user, pk)
    enrollments = Enrollment.objects.filter(course=course).select_related("student").order_by("student__name", "id")
    page, qs = paginate(request, enrollments)
    return render(request, "teacher/enrolled_students.html", {"course": course, "page": page, "querystring": qs})
