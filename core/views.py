import logging

from django.http import HttpResponseServerError
from django.shortcuts import redirect, render
from django.template.loader import render_to_string

logger = logging.getLogger("learnhub")


def confirm_page(request, *, title, message, confirm_label, cancel_url, danger=False, details=None):
    """Server-side confirmation step for every destructive/decisive action.

    GET renders this page; the action itself is only executed on the POST
    submitted from it, so confirmation cannot be skipped by URL manipulation
    for GET requests, and CSRF protects the POST.
    """
    return render(
        request,
        "confirm/confirm.html",
        {
            "title": title,
            "message": message,
            "confirm_label": confirm_label,
            "cancel_url": cancel_url,
            "danger": danger,
            "details": details or [],
        },
    )


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboards:home")
    return redirect("accounts:login")


def permission_denied(request, exception=None):
    return render(request, "errors/403.html", status=403)


def page_not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


def csrf_failure(request, reason=""):
    return render(request, "errors/403_csrf.html", status=403)


def server_error(request):
    # Standalone template: must not depend on anything that could also fail.
    return HttpResponseServerError(render_to_string("errors/500.html"))
