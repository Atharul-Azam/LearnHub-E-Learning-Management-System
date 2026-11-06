"""UC17: view progress and marks. A student only ever sees his/her own data."""
from django.shortcuts import render

from assignments.models import Submission
from core.decorators import student_required
from courses.access import get_student_enrollment

from .services import progress_summary, sync_enrollment_progress


@student_required
def course_progress(request, pk):
    enrollment = get_student_enrollment(request.user, pk)
    course = enrollment.course
    sync_enrollment_progress(enrollment)
    summary = progress_summary(request.user, course)
    # Filtering by student=request.user is what guarantees privacy between students.
    submissions = {
        s.assignment_id: s for s in Submission.objects.filter(student=request.user, assignment__course=course)
    }
    rows = []
    for assignment in course.assignments.order_by("deadline", "id"):
        rows.append({"assignment": assignment, "submission": submissions.get(assignment.pk)})
    return render(request, "progress/course_progress.html", {"course": course, "summary": summary, "rows": rows})
