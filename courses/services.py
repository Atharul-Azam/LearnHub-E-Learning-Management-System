"""Course business rules: visibility state machine (DD 6.4), search, enrollment."""
import logging

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404

from core.services import BusinessRuleError

from .models import Course, Enrollment

logger = logging.getLogger("learnhub")


def published_courses():
    return Course.objects.filter(visibility=Course.Visibility.PUBLISHED).select_related("teacher")


def published_categories():
    return (
        Course.objects.filter(visibility=Course.Visibility.PUBLISHED)
        .exclude(category="")
        .order_by("category")
        .values_list("category", flat=True)
        .distinct()
    )


def search_courses(queryset, query="", category=""):
    """UC13: every search word must match the title, description or category."""
    for word in (query or "").split():
        queryset = queryset.filter(
            Q(title__icontains=word) | Q(description__icontains=word) | Q(category__icontains=word)
        )
    if category:
        queryset = queryset.filter(category__iexact=category)
    return queryset


def get_owned_course_or_404(user, pk):
    """Ownership check: a teacher can reach only his/her own courses (SRS 8.4)."""
    return get_object_or_404(Course, pk=pk, teacher=user)


# ---- visibility (UC5) ------------------------------------------------------
@transaction.atomic
def set_visibility(course, visibility):
    course = Course.objects.select_for_update().get(pk=course.pk)
    if course.visibility == visibility:
        raise BusinessRuleError(f"The course is already {course.get_visibility_display().lower()}.")
    course.visibility = visibility
    course.save(update_fields=["visibility", "updated_at"])
    return course


def hide_course(course):
    return set_visibility(course, Course.Visibility.HIDDEN)


def publish_course(course):
    return set_visibility(course, Course.Visibility.PUBLISHED)


@transaction.atomic
def remove_course(course):
    """Permanently delete a course (UC5 / UC8).

    DD Fig-19 draws Assignment and LearningMaterial as compositions of Course,
    so they are deleted with it, together with enrollments and submissions that
    depend on them. Stored files are removed after the transaction commits.
    """
    course.delete()


# ---- enrollment (UC14) -----------------------------------------------------
@transaction.atomic
def enroll_student(student, course):
    """Create the enrollment. Returns True if created, False if it already existed."""
    if not Course.objects.filter(pk=course.pk, visibility=Course.Visibility.PUBLISHED).exists():
        raise BusinessRuleError("This course is not available for enrollment.")
    try:
        with transaction.atomic():
            _, created = Enrollment.objects.get_or_create(student=student, course=course)
    except IntegrityError:  # concurrent duplicate; the unique constraint won
        return False
    return created
