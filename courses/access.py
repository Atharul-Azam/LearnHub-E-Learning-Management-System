"""Object-level access helpers for student pages (SRS 18.4, 21.4)."""
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404

from .models import Course, Enrollment


def get_student_enrollment(user, course_pk):
    """Return the student's Enrollment in a *published* course.

    * unknown, hidden or removed course -> 404 (it is not accessible to students)
    * published public course the student has not enrolled in -> 403
    * private course the student has no access to -> 404
    """
    course = get_object_or_404(Course.objects.select_related("teacher"), pk=course_pk, visibility=Course.Visibility.PUBLISHED)
    enrollment = Enrollment.objects.filter(student=user, course=course).first()
    if enrollment is None:
        if course.is_private:
            raise Http404  # a private course must not even reveal that it exists
        raise PermissionDenied
    enrollment.course = course
    return enrollment
