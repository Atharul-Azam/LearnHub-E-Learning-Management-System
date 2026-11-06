"""Course progress (SRS 20.2; DD UC15 "updates the progress"; DD Fig-19 Enrollment.progress).

Definition used (docs/DECISIONS.md D-3): the "course activities" of a course
are its learning materials and its assignments.

    completed activities = materials the student has opened
                         + assignments the student has submitted
    progress %           = completed / (materials + assignments) * 100, rounded

The percentage is always recomputed from stored rows (MaterialAccess and
Submission) and cached in Enrollment.progress.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import MaterialAccess


def _counts(student, course):
    from assignments.models import Submission

    total_materials = course.materials.count()
    total_assignments = course.assignments.count()
    done_materials = MaterialAccess.objects.filter(student=student, material__course=course).count()
    done_assignments = Submission.objects.filter(student=student, assignment__course=course).count()
    return total_materials, done_materials, total_assignments, done_assignments


def compute_progress(student, course):
    """Return the progress percentage (0-100) calculated from stored data."""
    tm, dm, ta, da = _counts(student, course)
    total = tm + ta
    if total == 0:
        return 0
    done = min(dm + da, total)
    return (200 * done + total) // (2 * total)  # integer round-half-up


def progress_summary(student, course):
    tm, dm, ta, da = _counts(student, course)
    total = tm + ta
    percent = 0 if total == 0 else (200 * min(dm + da, total) + total) // (2 * total)
    return {
        "percent": percent,
        "materials_done": dm,
        "materials_total": tm,
        "assignments_done": da,
        "assignments_total": ta,
    }


def sync_enrollment_progress(enrollment):
    """Recompute and store Enrollment.progress. Returns the new value."""
    from courses.models import Enrollment

    value = compute_progress(enrollment.student, enrollment.course)
    Enrollment.objects.filter(pk=enrollment.pk).update(progress=value)
    enrollment.progress = value
    return value


def sync_student_progress(student, course):
    from courses.models import Enrollment

    enrollment = Enrollment.objects.filter(student=student, course=course).select_related("student", "course").first()
    if enrollment is not None:
        sync_enrollment_progress(enrollment)


def sync_course_progress(course):
    """Recompute progress for every enrollment (after materials/assignments change)."""
    from courses.models import Enrollment

    for enrollment in Enrollment.objects.filter(course=course).select_related("student", "course"):
        sync_enrollment_progress(enrollment)


def record_material_access(student, material):
    """UC15: remember that ``student`` opened ``material`` and update progress."""
    try:
        with transaction.atomic():
            MaterialAccess.objects.get_or_create(
                student=student, material=material, defaults={"first_accessed_at": timezone.now()}
            )
    except IntegrityError:  # concurrent first click: the row already exists
        pass
    sync_student_progress(student, material.course)


def viewed_material_ids(student, course):
    return set(
        MaterialAccess.objects.filter(student=student, material__course=course).values_list("material_id", flat=True)
    )
