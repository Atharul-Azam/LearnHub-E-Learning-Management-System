from .models import Notification


def notifications(request):
    """Unread badge and the five most recent notifications for the navigation bar."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    recent = list(Notification.objects.filter(recipient=user).order_by("-created_at", "-id")[:5])
    unread = Notification.objects.filter(recipient=user, read_at__isnull=True).count()
    return {"nav_notifications": recent, "nav_unread": unread}
