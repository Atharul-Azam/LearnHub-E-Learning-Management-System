"""UC1 Register, UC2 Login / Logout."""
import logging

from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import verification
from .forms import LoginForm, RegistrationForm, ResendVerificationForm
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
            sent = verification.send_verification_email(user, request)
            if user.role == User.Role.TEACHER:
                messages.success(
                    request,
                    "Your teacher account was created. Verify your e-mail address with the link we sent you; "
                    "you can log in once you have verified it AND an administrator has approved your account.",
                )
            else:
                messages.success(
                    request,
                    "Your student account was created. Verify your e-mail address with the link we sent you, then log in.",
                )
            if not sent:
                messages.warning(
                    request, "We could not send the verification e-mail right now. Use 'Resend verification e-mail' below."
                )
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
        elif not user.email_verified:
            note = ""
            if user.status == User.Status.PENDING:
                note = " Your teacher account also needs administrator approval."
            elif user.status in (User.Status.REJECTED, User.Status.DEACTIVATED):
                note = " " + STATUS_MESSAGES[user.status]
            form.add_error(None, "Please verify your e-mail address before logging in." + note)
            form.unverified = True
        elif user.status != User.Status.ACTIVE:
            # Credentials are correct, so the status can be explained safely.
            form.add_error(None, STATUS_MESSAGES.get(user.status, GENERIC_LOGIN_ERROR))
        else:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            target = request.POST.get("next") or request.GET.get("next") or ""
            if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(target)
            return redirect("dashboards:home")
    return render(
        request,
        "accounts/login.html",
        {"form": form, "next": request.GET.get("next", ""), "unverified": getattr(form, "unverified", False)},
    )


def verify_email(request, uidb64, token):
    result, user = verification.verify_email(uidb64, token)
    if result == verification.VERIFY_OK:
        if user.status == User.Status.PENDING:
            messages.success(
                request,
                "Your e-mail address is verified. Your teacher account still needs administrator approval before you can log in.",
            )
        else:
            messages.success(request, "Your e-mail address is verified. You can log in now.")
    elif result == verification.VERIFY_ALREADY:
        messages.info(request, "This e-mail address is already verified. This link cannot be used again.")
    else:
        messages.error(request, "This verification link is invalid or has expired. Request a new one below.")
        return redirect("accounts:resend_verification")
    return redirect("accounts:login")


def resend_verification(request):
    form = ResendVerificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        user = User.objects.filter(email__iexact=email).first()
        # The same answer is shown whether or not the account exists (no account enumeration).
        if user is not None and not user.email_verified and verification.resend_allowed(email):
            verification.send_verification_email(user, request)
        messages.info(
            request,
            "If an unverified account exists for that address, a new verification link has been sent. "
            "Please wait a minute before asking again.",
        )
        return redirect("accounts:login")
    return render(request, "accounts/resend_verification.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("accounts:login")
