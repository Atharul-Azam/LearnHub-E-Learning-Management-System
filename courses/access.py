"""Object-level access helpers for student pages (SRS 18.4, 21.4)."""
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from .models import Course, Enrollment


def get_student_enrollment(user, course_pk):
    """Return the student's Enrollment in a *published* course.

    * unknown, hidden or removed course -> 404 (it is not accessible to students)
    * published course the student has not enrolled in -> 403
    """
    course = get_object_or_404(Course.objects.select_related("teacher"), pk=course_pk, visibility=Course.Visibility.PUBLISHED)
    enrollment = Enrollment.objects.filter(student=user, course=course).first()
    if enrollment is None:
        raise PermissionDenied
    enrollment.course = course
    return enrollment
