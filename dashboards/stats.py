"""Dashboard and analytics figures. Everything is computed from stored records."""
from django.db.models import Avg, Count, Q
from django.utils import timezone

from assignments.models import Assignment, Submission
from community.models import Post
from courses.models import Course, CourseAccessRequest, Enrollment, Favourite


def teacher_totals(teacher):
    courses = Course.objects.filter(teacher=teacher)
    enrollments = Enrollment.objects.filter(course__teacher=teacher)
    submissions = Submission.objects.filter(assignment__course__teacher=teacher)
    return {
        "course_total": courses.count(),
        "public_total": courses.filter(access=Course.Access.PUBLIC).count(),
        "private_total": courses.filter(access=Course.Access.PRIVATE).count(),
        "enrollment_total": enrollments.count(),
        "student_total": enrollments.values("student").distinct().count(),
        "pending_requests": CourseAccessRequest.objects.filter(
            course__teacher=teacher, status=CourseAccessRequest.Status.PENDING
        ).count(),
        "submission_total": submissions.count(),
        "pending_reviews": submissions.filter(reviewed=False).count(),
        "reviewed_total": submissions.filter(reviewed=True).count(),
        "late_total": submissions.filter(is_late=True).count(),
    }


def teacher_course_performance(teacher):
    """One row per course: students, average progress, submissions, reviewed, pending."""
    rows = (
        Course.objects.filter(teacher=teacher)
        .annotate(
            students=Count("enrollments", distinct=True),
            avg_progress=Avg("enrollments__progress"),
            assignment_total=Count("assignments", distinct=True),
        )
        .order_by("-created_at", "-id")
    )
    # Alias names must differ from the Submission field names. The annotation used to be called
    # "reviewed": because values() was called first, Django skips its "annotation conflicts with a
    # field" check, and the later Q(reviewed=False) of "pending" resolved to the *aggregate* named
    # "reviewed" instead of the model field, i.e. COUNT(...) FILTER (WHERE COUNT(...)) - which SQLite
    # rejects with "misuse of aggregate function COUNT()".
    submission_counts = {
        row["assignment__course"]: row
        for row in Submission.objects.filter(assignment__course__teacher=teacher)
        .order_by()  # no Meta.ordering columns in the GROUP BY
        .values("assignment__course")
        .annotate(
            submissions_count=Count("id"),
            reviewed_count=Count("id", filter=Q(reviewed=True)),
            pending_count=Count("id", filter=Q(reviewed=False)),
        )
    }
    result = []
    for course in rows:
        counts = submission_counts.get(course.pk, {})
        result.append(
            {
                "course": course,
                "students": course.students,
                "avg_progress": round(course.avg_progress or 0),
                "assignments": course.assignment_total,
                "submissions": counts.get("submissions_count", 0),
                "reviewed": counts.get("reviewed_count", 0),
                "pending": counts.get("pending_count", 0),
            }
        )
    return result


def teacher_recent_activity(teacher, limit=6):
    """Latest enrolments, submissions and questions on the teacher's courses, newest first."""
    events = []
    for e in Enrollment.objects.filter(course__teacher=teacher).select_related("student", "course").order_by("-enrolled_at")[:limit]:
        events.append((e.enrolled_at, f"{e.student.name} enrolled in {e.course.title}"))
    for s in (
        Submission.objects.filter(assignment__course__teacher=teacher)
        .select_related("student", "assignment")
        .order_by("-submitted_at")[:limit]
    ):
        events.append((s.submitted_at, f"{s.student.name} submitted {s.assignment.title}"))
    for p in Post.objects.filter(course__teacher=teacher, parent__isnull=True).select_related("author", "course").order_by("-created_at")[:limit]:
        who = p.author.name if p.author else "A former student"
        events.append((p.created_at, f"{who} asked a question in {p.course.title}"))
    events.sort(key=lambda item: item[0], reverse=True)
    return events[:limit]


def student_overview(student):
    now = timezone.now()
    enrollments = (
        Enrollment.objects.filter(student=student, course__visibility=Course.Visibility.PUBLISHED)
        .select_related("course", "course__teacher")
        .order_by("-enrolled_at", "-id")
    )
    items = list(enrollments)
    total = len(items)
    completed = sum(1 for e in items if e.progress == 100)
    overall = round(sum(e.progress for e in items) / total) if total else 0
    course_ids = [e.course_id for e in items]
    submitted_ids = set(Submission.objects.filter(student=student).values_list("assignment_id", flat=True))
    open_assignments = list(
        Assignment.objects.filter(course_id__in=course_ids).exclude(pk__in=submitted_ids).select_related("course").order_by("deadline", "id")
    )
    for a in open_assignments:
        a.overdue = a.deadline < now
    recent = sorted((e for e in items if e.last_accessed_at), key=lambda e: e.last_accessed_at, reverse=True)[:4]
    marks = (
        Submission.objects.filter(student=student, reviewed=True)
        .select_related("assignment", "assignment__course")
        .order_by("-reviewed_at", "-id")[:5]
    )
    favourites = (
        Favourite.objects.filter(student=student, course__visibility=Course.Visibility.PUBLISHED)
        .select_related("course", "course__teacher")
        .order_by("-created_at")
    )
    visible_favourites = [f for f in favourites if not f.course.is_private or f.course_id in course_ids][:4]
    return {
        "enrollments": items[:6],
        "enrollment_total": total,
        "completed_total": completed,
        "overall_progress": overall,
        "recent_courses": recent,
        "pending_assignments": open_assignments[:6],
        "pending_total": len(open_assignments),
        "recent_marks": marks,
        "favourites": visible_favourites,
    }
