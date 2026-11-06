"""UC6 platform statistics and the three role dashboards (SRS 3.1-3.4)."""
from django.shortcuts import redirect, render

from accounts.models import User
from assignments.models import Submission
from core.decorators import admin_required, login_required_any, student_required, teacher_required
from courses.models import Course, Enrollment


@login_required_any
def home(request):
    """Send each user to the dashboard of his/her role (SRS 3)."""
    target = {
        User.Role.ADMIN: "dashboards:admin",
        User.Role.TEACHER: "dashboards:teacher",
        User.Role.STUDENT: "dashboards:student",
    }[request.user.role]
    return redirect(target)


def platform_statistics():
    """Computed from the database on every call - never cached or hard-coded (SRS 7.3)."""
    teachers = User.objects.filter(role=User.Role.TEACHER)
    return {
        "students": User.objects.filter(role=User.Role.STUDENT).count(),
        # "Approved" = a teacher who has passed approval: Active, or Deactivated after approval.
        "teachers": teachers.filter(status__in=[User.Status.ACTIVE, User.Status.DEACTIVATED]).count(),
        "courses": Course.objects.count(),
        "enrollments": Enrollment.objects.count(),
        "pending_teachers": teachers.filter(status=User.Status.PENDING).count(),
    }


@admin_required
def admin_dashboard(request):
    return render(request, "dashboards/admin.html", {"stats": platform_statistics()})


@teacher_required
def teacher_dashboard(request):
    from django.db.models import Count

    courses = (
        Course.objects.filter(teacher=request.user)
        .annotate(enrollment_total=Count("enrollments", distinct=True))
        .order_by("-created_at", "-id")
    )
    pending_reviews = Submission.objects.filter(assignment__course__teacher=request.user, reviewed=False).count()
    return render(
        request,
        "dashboards/teacher.html",
        {"courses": courses[:6], "course_total": courses.count(), "pending_reviews": pending_reviews},
    )


@student_required
def student_dashboard(request):
    enrollments = (
        Enrollment.objects.filter(student=request.user, course__visibility=Course.Visibility.PUBLISHED)
        .select_related("course", "course__teacher")
        .order_by("-enrolled_at", "-id")
    )
    return render(request, "dashboards/student.html", {"enrollments": enrollments[:6], "enrollment_total": enrollments.count()})
