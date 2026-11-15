"""Profile, settings (appearance, notifications, security), picture serving, self-service deletion."""
import logging

from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.db import DatabaseError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.decorators import login_required_any
from core.files import file_response
from core.services import BusinessRuleError

from . import services
from .forms import (
    AppearanceForm,
    DeleteAccountForm,
    NotificationPreferencesForm,
    ProfileForm,
    StyledPasswordChangeForm,
)
from .models import User
from .sessions import revoke_sessions

logger = logging.getLogger("learnhub")


def profile_context(user):
    """Role-specific figures, all computed from stored records."""
    from courses.models import Course, Enrollment, Favourite

    data = {}
    if user.role == User.Role.TEACHER:
        data["courses_created"] = Course.objects.filter(teacher=user).count()
        data["students_total"] = (
            Enrollment.objects.filter(course__teacher=user).values("student").distinct().count()
        )
    elif user.role == User.Role.STUDENT:
        enrollments = Enrollment.objects.filter(student=user, course__visibility=Course.Visibility.PUBLISHED)
        data["enrolled_courses"] = enrollments.select_related("course", "course__teacher").order_by("-enrolled_at")[:6]
        data["enrolled_total"] = enrollments.count()
        data["completed_total"] = enrollments.filter(progress=100).count()
        total = data["enrolled_total"]
        data["overall_progress"] = round(sum(enrollments.values_list("progress", flat=True)) / total) if total else 0
        data["favourite_total"] = Favourite.objects.filter(student=user).count()
    return data


@login_required_any
def profile(request):
    return render(request, "accounts/profile.html", {"profile_user": request.user, **profile_context(request.user)})


@login_required_any
def settings_home(request):
    return render(request, "accounts/settings_home.html", {"section": "account"})


@login_required_any
def settings_profile(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except DatabaseError:
            logger.exception("Profile update failed")
            messages.error(request, "Your profile could not be saved. Please try again.")
        else:
            messages.success(request, "Your profile was updated.")
            return redirect("accounts:settings_profile")
    elif request.method == "POST":
        messages.error(request, "Your profile was not saved. Please correct the errors below.")
    return render(request, "accounts/settings_profile.html", {"form": form, "section": "profile"})


@login_required_any
def settings_password(request):
    form = StyledPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)  # keeps this session, ends the old hash everywhere else
        revoke_sessions(user, keep_key=request.session.session_key)
        messages.success(request, "Your password was changed. Other devices were signed out.")
        return redirect("accounts:settings_password")
    return render(request, "accounts/settings_password.html", {"form": form, "section": "password"})


@login_required_any
def settings_notifications(request):
    form = NotificationPreferencesForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Notification preferences saved.")
        return redirect("accounts:settings_notifications")
    return render(request, "accounts/settings_notifications.html", {"form": form, "section": "notifications"})


@login_required_any
def settings_appearance(request):
    form = AppearanceForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()  # stored on the account, so it survives logout and login
        messages.success(request, "Appearance saved.")
        return redirect("accounts:settings_appearance")
    return render(request, "accounts/settings_appearance.html", {"form": form, "section": "appearance"})


@login_required_any
def settings_security(request):
    return render(request, "accounts/settings_security.html", {"section": "security"})


@login_required_any
@require_POST
def sign_out_other_devices(request):
    count = revoke_sessions(request.user, keep_key=request.session.session_key)
    messages.success(request, f"Signed out of {count} other session(s).")
    return redirect("accounts:settings_security")


@login_required_any
def settings_delete(request):
    """Self-service account deletion. Only ever deletes request.user (never another account)."""
    user = request.user
    blocker = None
    if user.role == User.Role.ADMIN:
        blocker = "Administrator accounts cannot be deleted here."
    elif user.role == User.Role.TEACHER and user.courses.exists():
        blocker = "You still own courses. Remove or hand over your courses first, then you can delete your account."
    form = DeleteAccountForm(request.POST or None, user=user)
    if request.method == "POST" and blocker is None and form.is_valid():
        try:
            revoke_sessions(user)
            services.remove_own_account(user)
        except BusinessRuleError as exc:
            messages.error(request, str(exc))
        except DatabaseError:
            logger.exception("Account deletion failed")
            messages.error(request, "Your account could not be deleted. Please try again.")
        else:
            logout(request)
            messages.success(request, "Your account and personal data were permanently deleted. Goodbye!")
            return redirect("accounts:login")
    return render(request, "accounts/settings_delete.html", {"form": form, "blocker": blocker, "section": "delete"})


@login_required_any
def avatar_file(request, pk):
    """Profile pictures are visible to signed-in users only (they appear in discussions)."""
    owner = get_object_or_404(User, pk=pk)
    if not owner.profile_picture:
        raise Http404
    return file_response(owner.profile_picture, f"avatar-{owner.pk}.{owner.profile_picture.name.rsplit('.', 1)[-1]}")
