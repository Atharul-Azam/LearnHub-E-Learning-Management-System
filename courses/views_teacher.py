"""Teacher views: UC7 create, UC8 edit/delete, UC11 enrolled students."""
import logging

from django.contrib import messages
from django.db import DatabaseError
from django.db.models import Count
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from core.decorators import teacher_required
from core.pagination import paginate
from core.views import confirm_page

from core.services import BusinessRuleError

from . import private, services
from .forms import CourseForm
from .models import Course, CourseAccessRequest, Enrollment

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
            "pending_requests": course.access_requests.filter(status="pending").count(),
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


# ---------------------------------------------------- sharing and access requests
@teacher_required
def teacher_sharing(request, pk):
    """Share a public course link or manage a private course's invitation link."""
    course = services.get_owned_course_or_404(request.user, pk)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "generate":
                private.generate_invite(course, request.POST.get("expiry", "never"))
                messages.success(request, "A new invitation link was created. The previous link no longer works.")
            elif action == "disable":
                private.disable_invite(course)
                messages.success(request, "The invitation link was disabled. Nobody can use it any more.")
            else:
                messages.error(request, "Unknown action.")
        except BusinessRuleError as exc:
            messages.error(request, str(exc))
        return redirect("courses:teacher_sharing", pk=pk)
    if course.is_private:
        link = private.invite_url(course, request)
    else:
        link = request.build_absolute_uri(reverse("courses:detail", args=[course.pk]))
    return render(
        request,
        "teacher/course_sharing.html",
        {"course": course, "share_url": link, "expiry_choices": list(private.EXPIRY_CHOICES)},
    )


@teacher_required
def access_requests(request, pk=None):
    """Pending requests across all of the teacher's courses, or every request for one course."""
    course = services.get_owned_course_or_404(request.user, pk) if pk else None
    requests_qs = CourseAccessRequest.objects.filter(course__teacher=request.user).select_related("course", "student")
    if course:
        requests_qs = requests_qs.filter(course=course)
    else:
        requests_qs = requests_qs.filter(status=CourseAccessRequest.Status.PENDING)
    page, qs = paginate(request, requests_qs.order_by("-requested_at", "-id"))
    return render(request, "teacher/access_requests.html", {"course": course, "page": page, "querystring": qs})


def _decide(request, pk, action):
    try:
        access = action(request.user, pk)
    except BusinessRuleError as exc:
        messages.error(request, str(exc))
        return redirect("courses:teacher_requests_all")
    messages.success(request, f"{access.student.name}: request {access.get_status_display().lower()}.")
    return redirect("courses:teacher_requests", pk=access.course_id)


@teacher_required
def request_approve(request, pk):
    if request.method != "POST":
        return redirect("courses:teacher_requests_all")
    return _decide(request, pk, private.approve_request)


@teacher_required
def request_reject(request, pk):
    if request.method != "POST":
        return redirect("courses:teacher_requests_all")
    return _decide(request, pk, private.reject_request)


@teacher_required
def student_revoke(request, pk, student_pk):
    course = services.get_owned_course_or_404(request.user, pk)
    student = Enrollment.objects.filter(course=course, student_id=student_pk).select_related("student").first()
    if student is None:
        raise Http404
    student = student.student
    if request.method == "POST":
        try:
            private.revoke_student(request.user, course, student)
        except BusinessRuleError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"{student.name} no longer has access to '{course.title}'.")
        return redirect("courses:teacher_students", pk=pk)
    return confirm_page(
        request,
        title="Revoke access",
        message=f"Remove {student.name} from '{course.title}'? They lose access to its materials and assignments "
        "(their submissions and marks are kept). They can only return if you approve them again.",
        confirm_label="Revoke access",
        cancel_url=reverse("courses:teacher_students", args=[pk]),
        danger=True,
    )
