"""Administrator views: UC3 (teacher requests) and UC4 (manage accounts)."""
import logging

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.decorators import admin_required
from core.pagination import paginate
from core.services import BusinessRuleError
from core.views import confirm_page

from . import services
from .models import User

logger = logging.getLogger("learnhub")


# ------------------------------------------------------------------ UC3
@admin_required
def teacher_requests(request):
    pending = User.objects.filter(role=User.Role.TEACHER, status=User.Status.PENDING).order_by("date_joined")
    page, qs = paginate(request, pending)
    return render(request, "admin_panel/teacher_requests.html", {"page": page, "querystring": qs})


@admin_required
def teacher_request_detail(request, pk):
    teacher = get_object_or_404(User, pk=pk, role=User.Role.TEACHER)
    return render(request, "admin_panel/teacher_request_detail.html", {"teacher": teacher})


def _teacher_decision(request, pk, *, service, title, verb, past, danger):
    teacher = get_object_or_404(User, pk=pk, role=User.Role.TEACHER)
    if request.method == "POST":
        try:
            service(teacher, request.user)
        except BusinessRuleError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Teacher account for {teacher.name} was {past}.")
        return redirect("accounts:teacher_requests")
    return confirm_page(
        request,
        title=title,
        message=f"Do you want to {verb} the teacher registration of {teacher.name} ({teacher.email})?",
        confirm_label=verb.capitalize(),
        cancel_url=reverse("accounts:teacher_request_detail", args=[pk]),
        danger=danger,
    )


@admin_required
def approve_teacher(request, pk):
    return _teacher_decision(request, pk, service=services.approve_teacher, title="Approve teacher", verb="approve", past="approved", danger=False)


@admin_required
def reject_teacher(request, pk):
    return _teacher_decision(request, pk, service=services.reject_teacher, title="Reject teacher", verb="reject", past="rejected", danger=True)


# ------------------------------------------------------------------ UC4
@admin_required
def user_list(request):
    users = services.managed_accounts()
    role = request.GET.get("role", "")
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    if role in {User.Role.STUDENT, User.Role.TEACHER}:
        users = users.filter(role=role)
    if status in User.Status.values:
        users = users.filter(status=status)
    if q:
        users = users.filter(Q(name__icontains=q) | Q(email__icontains=q))
    page, qs = paginate(request, users.order_by("name", "email"))
    return render(
        request,
        "admin_panel/user_list.html",
        {
            "page": page,
            "querystring": qs,
            "role": role,
            "status": status,
            "q": q,
            "roles": [(User.Role.STUDENT.value, "Students"), (User.Role.TEACHER.value, "Teachers")],
            "statuses": User.Status.choices,
        },
    )


@admin_required
def user_detail(request, pk):
    account = get_object_or_404(services.managed_accounts(), pk=pk)
    context = {"account": account}
    if account.role == User.Role.TEACHER:
        context["course_count"] = account.courses.count()
    else:
        context["enrollment_count"] = account.enrollments.count()
    return render(request, "admin_panel/user_detail.html", context)


def _account_action(request, pk, *, service, title, verb, past, danger):
    account = get_object_or_404(services.managed_accounts(), pk=pk)
    if request.method == "POST":
        try:
            service(account, request.user) if service is not services.remove_account else service(account)
        except BusinessRuleError as exc:
            messages.error(request, str(exc))
            return redirect("accounts:user_detail", pk=pk)
        messages.success(request, f"Account of {account.name} was {past}.")
        if service is services.remove_account:
            return redirect("accounts:user_list")
        return redirect("accounts:user_detail", pk=pk)
    return confirm_page(
        request,
        title=title,
        message=f"Do you want to {verb} the account of {account.name} ({account.email})?"
        + (" This cannot be undone." if danger else ""),
        confirm_label=verb.capitalize(),
        cancel_url=reverse("accounts:user_detail", args=[pk]),
        danger=danger,
    )


@admin_required
def activate_user(request, pk):
    return _account_action(request, pk, service=services.activate_account, title="Activate account", verb="activate", past="activated", danger=False)


@admin_required
def deactivate_user(request, pk):
    return _account_action(request, pk, service=services.deactivate_account, title="Deactivate account", verb="deactivate", past="deactivated", danger=True)


@admin_required
def remove_user(request, pk):
    return _account_action(request, pk, service=services.remove_account, title="Remove account", verb="remove", past="removed", danger=True)
