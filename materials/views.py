"""UC9 upload/replace/remove (teacher) and UC15 access (student)."""
import logging

from django.contrib import messages
from django.db import DatabaseError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.decorators import login_required_any, teacher_required
from core.files import file_response
from core.views import confirm_page
from courses.access import get_student_enrollment
from courses.services import get_owned_course_or_404
from progress.services import record_material_access, sync_course_progress

from .forms import MaterialForm
from .models import LearningMaterial

logger = logging.getLogger("learnhub")


def _owned_material_or_404(user, pk):
    return get_object_or_404(LearningMaterial.objects.select_related("course"), pk=pk, course__teacher=user)


@teacher_required
def material_add(request, course_pk):
    course = get_owned_course_or_404(request.user, course_pk)
    form = MaterialForm(request.POST or None, request.FILES or None, instance=LearningMaterial(course=course))
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                material = form.save()
                sync_course_progress(course)
        except DatabaseError:
            logger.exception("Material upload failed")
            messages.error(request, "The material could not be saved. Please try again.")
        else:
            messages.success(request, f"Material '{material.title}' was uploaded.")
            return redirect("courses:teacher_detail", pk=course.pk)
    elif request.method == "POST":
        messages.error(request, "The material was not saved. Please correct the errors below.")
    return render(request, "materials/material_form.html", {"form": form, "course": course, "editing": False})


@teacher_required
def material_edit(request, pk):
    material = _owned_material_or_404(request.user, pk)
    form = MaterialForm(request.POST or None, request.FILES or None, instance=material)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except DatabaseError:
            logger.exception("Material update failed")
            messages.error(request, "The changes could not be saved. Please try again.")
        else:
            messages.success(request, "The material was updated.")
            return redirect("courses:teacher_detail", pk=material.course_id)
    elif request.method == "POST":
        messages.error(request, "The changes were not saved. Please correct the errors below.")
    return render(
        request, "materials/material_form.html", {"form": form, "course": material.course, "material": material, "editing": True}
    )


@teacher_required
def material_delete(request, pk):
    material = _owned_material_or_404(request.user, pk)
    course = material.course
    if request.method == "POST":
        title = material.title
        try:
            with transaction.atomic():
                material.delete()
                sync_course_progress(course)
        except DatabaseError:
            logger.exception("Material removal failed")
            messages.error(request, "The material could not be removed. Please try again.")
        else:
            messages.success(request, f"Material '{title}' was removed.")
        return redirect("courses:teacher_detail", pk=course.pk)
    return confirm_page(
        request,
        title="Remove material",
        message=f"Remove the material '{material.title}'? The uploaded file will be deleted.",
        confirm_label="Remove material",
        cancel_url=reverse("courses:teacher_detail", args=[course.pk]),
        danger=True,
    )


@login_required_any
def material_file(request, pk):
    """View (inline where safe) or download (?download=1) a material.

    Student: must be enrolled in the (published) course; the access is recorded
    and the progress updated. Owning teacher and administrator: allowed, nothing
    recorded. Anyone else: denied.
    """
    material = get_object_or_404(LearningMaterial.objects.select_related("course"), pk=pk)
    user = request.user
    if user.is_student:
        get_student_enrollment(user, material.course_id)  # 404 / 403 on failure
        record_material_access(user, material)
    elif user.is_teacher:
        if material.course.teacher_id != user.pk:
            return render(request, "errors/404.html", status=404)
    elif not user.is_admin:
        return render(request, "errors/403.html", status=403)
    return file_response(material.file, material.original_name, force_download=request.GET.get("download") == "1")
