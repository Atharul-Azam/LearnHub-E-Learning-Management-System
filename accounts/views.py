"""UC1 Register, UC2 Login / Logout."""
import logging

from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import LoginForm, RegistrationForm
from .models import User

logger = logging.getLogger("learnhub")

GENERIC_LOGIN_ERROR = "The e-mail address or password is incorrect."
STATUS_MESSAGES = {
    User.Status.PENDING: "Your teacher account is waiting for administrator approval. You cannot log in until it is approved.",
    User.Status.REJECTED: "Your teacher registration was rejected by an administrator. This account cannot be used to log in.",
    User.Status.DEACTIVATED: "Your account has been deactivated. Please contact an administrator.",
}


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboards:home")
    form = RegistrationForm(request.POST or None, initial={"account_type": request.GET.get("type", "student")})
    if request.method == "POST" and form.is_valid():
        user = form.save()
        if user is not None:
            if user.role == User.Role.TEACHER:
                messages.success(
                    request,
                    "Your teacher account was created and is waiting for administrator approval. "
                    "You will be able to log in once it is approved.",
                )
            else:
                messages.success(request, "Your student account was created. You can log in now.")
            return redirect("accounts:login")
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboards:home")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            User().set_password(password)  # keep timing similar; reveals nothing
            form.add_error(None, GENERIC_LOGIN_ERROR)
        elif not user.check_password(password):
            form.add_error(None, GENERIC_LOGIN_ERROR)
        elif user.status != User.Status.ACTIVE:
            # Credentials are correct, so the status can be explained safely.
            form.add_error(None, STATUS_MESSAGES.get(user.status, GENERIC_LOGIN_ERROR))
        else:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            target = request.POST.get("next") or request.GET.get("next") or ""
            if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(target)
            return redirect("dashboards:home")
    return render(request, "accounts/login.html", {"form": form, "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("accounts:login")
