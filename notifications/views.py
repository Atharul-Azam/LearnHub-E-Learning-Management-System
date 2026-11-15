from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.decorators import login_required_any
from core.pagination import paginate

from . import services
from .models import Notification


@login_required_any
def notification_list(request):
    if request.user.is_student:
        services.generate_deadline_reminders(request.user)
    only_unread = request.GET.get("filter") == "unread"
    notes = Notification.objects.filter(recipient=request.user)
    if only_unread:
        notes = notes.filter(read_at__isnull=True)
    page, qs = paginate(request, notes)
    return render(
        request,
        "notifications/list.html",
        {"page": page, "querystring": qs, "only_unread": only_unread, "unread_total": services.unread_count(request.user)},
    )


@login_required_any
@require_POST
def notification_open(request, pk):
    """Mark the user's own notification as read, then go where it points."""
    note = services.mark_read(request.user, pk)
    if note is None:
        messages.error(request, "That notification was not found.")
        return redirect("notifications:list")
    target = note.url
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}) and target.startswith("/"):
        return redirect(target)
    return redirect("notifications:list")


@login_required_any
@require_POST
def notification_read_all(request):
    count = services.mark_all_read(request.user)
    messages.success(request, f"{count} notification(s) marked as read.")
    return redirect("notifications:list")
