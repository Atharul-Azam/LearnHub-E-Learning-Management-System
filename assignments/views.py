"""UC10 publish assignment, UC12 review, UC16 submit, plus controlled file access."""
import logging

from django.contrib import messages
from django.db import DatabaseError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.decorators import login_required_any, student_required, teacher_required
from core.files import file_response
from core.pagination import paginate
from core.services import BusinessRuleError
from core.views import confirm_page
from courses.access import get_student_enrollment
from courses.models import Enrollment
from courses.services import get_owned_course_or_404
from progress.services import sync_course_progress

from . import services
from .forms import AssignmentForm, ReviewForm, SubmissionForm
from .models import Assignment, Submission

logger = logging.getLogger("learnhub")


def _owned_assignment_or_404(user, pk):
    return get_object_or_404(Assignment.objects.select_related("course"), pk=pk, course__teacher=user)


def _owned_submission_or_404(user, pk):
    return get_object_or_404(
        Submission.objects.select_related("assignment", "assignment__course", "student"),
        pk=pk,
        assignment__course__teacher=user,
    )


# ------------------------------------------------------------ teacher: UC10
@teacher_required
def assignment_add(request, course_pk):
    course = get_owned_course_or_404(request.user, course_pk)
    form = AssignmentForm(request.POST or None, request.FILES or None, instance=Assignment(course=course))
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                assignment = form.save()
                sync_course_progress(course)
        except DatabaseError:
            logger.exception("Assignment creation failed")
            messages.error(request, "The assignment could not be saved. Please try again.")
        else:
            messages.success(request, f"Assignment '{assignment.title}' was published to the enrolled students.")
            return redirect("courses:teacher_detail", pk=course.pk)
    elif request.method == "POST":
        messages.error(request, "The assignment was not saved. Please correct the errors below.")
    return render(request, "assignments/assignment_form.html", {"form": form, "course": course, "editing": False})


@teacher_required
def assignment_edit(request, pk):
    assignment = _owned_assignment_or_404(request.user, pk)
    form = AssignmentForm(request.POST or None, request.FILES or None, instance=assignment)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except DatabaseError:
            logger.exception("Assignment update failed")
            messages.error(request, "The changes could not be saved. Please try again.")
        else:
            messages.success(request, "The assignment was updated.")
            return redirect("assignments:teacher_detail", pk=assignment.pk)
    elif request.method == "POST":
        messages.error(request, "The changes were not saved. Please correct the errors below.")
    return render(
        request,
        "assignments/assignment_form.html",
        {"form": form, "course": assignment.course, "assignment": assignment, "editing": True},
    )


@teacher_required
def assignment_delete(request, pk):
    assignment = _owned_assignment_or_404(request.user, pk)
    course = assignment.course
    if request.method == "POST":
        title = assignment.title
        try:
            with transaction.atomic():
                assignment.delete()
                sync_course_progress(course)
        except DatabaseError:
            logger.exception("Assignment removal failed")
            messages.error(request, "The assignment could not be removed. Please try again.")
        else:
            messages.success(request, f"Assignment '{title}' was removed.")
        return redirect("courses:teacher_detail", pk=course.pk)
    submission_total = assignment.submissions.count()
    return confirm_page(
        request,
        title="Remove assignment",
        message=f"Remove the assignment '{assignment.title}'? "
        f"{submission_total} student submission(s), marks and feedback will be permanently deleted.",
        confirm_label="Remove assignment",
        cancel_url=reverse("assignments:teacher_detail", args=[assignment.pk]),
        danger=True,
    )


# ----------------------------------------------------- teacher: UC12 review
@teacher_required
def assignment_detail(request, pk):
    assignment = _owned_assignment_or_404(request.user, pk)
    submissions = assignment.submissions.select_related("student").order_by("submitted_at", "id")
    page, qs = paginate(request, submissions)
    enrolled_total = Enrollment.objects.filter(course=assignment.course).count()
    return render(
        request,
        "assignments/teacher_assignment_detail.html",
        {
            "assignment": assignment,
            "course": assignment.course,
            "page": page,
            "querystring": qs,
            "submission_total": assignment.submissions.count(),
            "enrolled_total": enrolled_total,
        },
    )


@teacher_required
def review_submission(request, pk):
    submission = _owned_submission_or_404(request.user, pk)
    assignment = submission.assignment
    initial = {"marks": submission.marks, "feedback": submission.feedback} if submission.reviewed else None
    form = ReviewForm(request.POST or None, assignment=assignment, initial=initial)
    if request.method == "POST":
        if form.is_valid():
            try:
                services.save_review(submission, form.cleaned_data["marks"], form.cleaned_data["feedback"])
            except BusinessRuleError as exc:
                form.add_error("marks", str(exc))
            except DatabaseError:
                logger.exception("Saving review failed")
                messages.error(request, "The review could not be saved. Please try again.")
            else:
                messages.success(request, f"Marks and feedback for {submission.student.name} were saved.")
                return redirect("assignments:teacher_detail", pk=assignment.pk)
        else:
            messages.error(request, "The review was not saved. Please correct the errors below.")
    return render(
        request,
        "assignments/review_form.html",
        {"form": form, "submission": submission, "assignment": assignment, "course": assignment.course},
    )


# ------------------------------------------------------------ student: UC16
@student_required
def student_assignment(request, pk):
    assignment = get_object_or_404(Assignment.objects.select_related("course"), pk=pk)
    get_student_enrollment(request.user, assignment.course_id)  # 404 hidden/removed, 403 not enrolled
    submission = Submission.objects.filter(assignment=assignment, student=request.user).first()
    form = SubmissionForm()
    if request.method == "POST":
        form = SubmissionForm(request.POST, request.FILES)
        if submission is not None:
            messages.error(request, "You have already submitted this assignment.")
            return redirect("assignments:student_detail", pk=pk)
        if form.is_valid():
            try:
                submission = services.submit_assignment(request.user, assignment, form.cleaned_data["file"])
            except BusinessRuleError as exc:
                messages.error(request, str(exc))
                return redirect("assignments:student_detail", pk=pk)
            except Exception:
                logger.exception("Submission failed")
                messages.error(request, "The upload failed. Your previous state was not changed. Please try again.")
            else:
                when = submission.submitted_at
                messages.success(
                    request,
                    "Your work was submitted successfully at "
                    f"{timezone.localtime(when):%d %b %Y, %H:%M}"
                    + (" (late)." if submission.is_late else "."),
                )
                return redirect("assignments:student_detail", pk=pk)
        else:
            messages.error(request, "The file was not accepted. Nothing was submitted.")
    return render(
        request,
        "assignments/student_assignment.html",
        {"assignment": assignment, "course": assignment.course, "submission": submission, "form": form},
    )


# -------------------------------------------------------- controlled files
@login_required_any
def attachment_file(request, pk):
    assignment = get_object_or_404(Assignment.objects.select_related("course"), pk=pk)
    user = request.user
    if user.is_student:
        get_student_enrollment(user, assignment.course_id)
    elif user.is_teacher:
        if assignment.course.teacher_id != user.pk:
            return render(request, "errors/404.html", status=404)
    elif not user.is_admin:
        return render(request, "errors/403.html", status=403)
    return file_response(
        assignment.attachment, assignment.attachment_name, force_download=request.GET.get("download") == "1"
    )


@login_required_any
def submission_file(request, pk):
    """A submitted file is visible only to its student and the owning teacher."""
    submission = get_object_or_404(
        Submission.objects.select_related("assignment__course"), pk=pk
    )
    user = request.user
    allowed = (user.is_student and submission.student_id == user.pk) or (
        user.is_teacher and submission.assignment.course.teacher_id == user.pk
    )
    if not allowed:
        return render(request, "errors/404.html", status=404)
    return file_response(
        submission.file, submission.original_name, force_download=request.GET.get("download") == "1"
    )
