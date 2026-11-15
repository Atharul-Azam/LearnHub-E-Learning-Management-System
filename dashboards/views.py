"""UC6 platform statistics and the three role dashboards (SRS 3.1-3.4)."""
from django.shortcuts import redirect, render

from accounts.models import User
from core.decorators import admin_required, login_required_any, student_required, teacher_required
from courses.models import Course, CourseAccessRequest, Enrollment
from notifications import services as notification_services

from . import stats


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
    totals = stats.teacher_totals(request.user)
    courses = Course.objects.filter(teacher=request.user).order_by("-created_at", "-id")
    return render(
        request,
        "dashboards/teacher.html",
        {
            **totals,
            "courses": courses[:6],
            "performance": stats.teacher_course_performance(request.user)[:6],
            "activity": stats.teacher_recent_activity(request.user),
            "pending_request_list": CourseAccessRequest.objects.filter(
                course__teacher=request.user, status=CourseAccessRequest.Status.PENDING
            ).select_related("course", "student")[:5],
        },
    )


@teacher_required
def teacher_analytics(request):
    """Only the signed-in teacher's own courses are counted (every query is filtered by teacher)."""
    totals = stats.teacher_totals(request.user)
    performance = stats.teacher_course_performance(request.user)
    most = max((row["students"] for row in performance), default=0)
    for row in performance:
        row["bar"] = round(row["students"] / most * 100) if most else 0
    return render(request, "dashboards/analytics.html", {**totals, "performance": performance})


@student_required
def student_dashboard(request):
    notification_services.generate_deadline_reminders(request.user)
    return render(request, "dashboards/student.html", stats.student_overview(request.user))
