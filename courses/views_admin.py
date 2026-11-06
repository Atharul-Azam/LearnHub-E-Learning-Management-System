"""Administrator views: UC5 manage courses."""
from django.contrib import messages
from django.db import DatabaseError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.decorators import admin_required
from core.pagination import paginate
from core.services import BusinessRuleError
from core.views import confirm_page

from . import services
from .models import Course


@admin_required
def admin_list(request):
    courses = Course.objects.select_related("teacher").annotate(enrollment_total=Count("enrollments", distinct=True))
    visibility = request.GET.get("visibility", "")
    q = request.GET.get("q", "").strip()
    if visibility in Course.Visibility.values:
        courses = courses.filter(visibility=visibility)
    if q:
        courses = courses.filter(
            Q(title__icontains=q) | Q(category__icontains=q) | Q(teacher__name__icontains=q)
        )
    page, qs = paginate(request, courses.order_by("-created_at", "-id"))
    return render(
        request,
        "admin_panel/course_list.html",
        {"page": page, "querystring": qs, "visibility": visibility, "q": q, "visibilities": Course.Visibility.choices},
    )


@admin_required
def admin_detail(request, pk):
    course = get_object_or_404(Course.objects.select_related("teacher"), pk=pk)
    return render(
        request,
        "admin_panel/course_detail.html",
        {
            "course": course,
            "materials": course.materials.order_by("created_at", "id"),
            "assignments": course.assignments.order_by("deadline", "id"),
            "enrollment_total": course.enrollments.count(),
        },
    )


def _visibility_action(request, pk, *, service, title, verb, past):
    course = get_object_or_404(Course, pk=pk)
    if request.method == "POST":
        try:
            service(course)
        except BusinessRuleError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Course '{course.title}' was {past}.")
        return redirect("courses:admin_detail", pk=pk)
    return confirm_page(
        request,
        title=title,
        message=f"Do you want to {verb} the course '{course.title}'?",
        confirm_label=verb.capitalize(),
        cancel_url=reverse("courses:admin_detail", args=[pk]),
        danger=(verb == "hide"),
    )


@admin_required
def admin_hide(request, pk):
    return _visibility_action(request, pk, service=services.hide_course, title="Hide course", verb="hide", past="hidden from students")


@admin_required
def admin_publish(request, pk):
    return _visibility_action(request, pk, service=services.publish_course, title="Publish course", verb="publish", past="published")


@admin_required
def admin_remove(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if request.method == "POST":
        title = course.title
        try:
            services.remove_course(course)
        except DatabaseError:
            messages.error(request, "The course could not be removed. Please try again.")
            return redirect("courses:admin_detail", pk=pk)
        messages.success(request, f"Course '{title}' was removed.")
        return redirect("courses:admin_list")
    return confirm_page(
        request,
        title="Remove course",
        message=f"Remove the course '{course.title}'? Its materials, assignments, enrollments and "
        "submissions will be permanently deleted. This cannot be undone.",
        confirm_label="Remove course",
        cancel_url=reverse("courses:admin_detail", args=[pk]),
        danger=True,
    )
