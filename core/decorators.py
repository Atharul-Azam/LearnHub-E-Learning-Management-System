"""Server-side role-based access control (SRS 21.2-21.4)."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Require an authenticated, Active user whose role is one of ``roles``.

    Anonymous users are redirected to the login page; authenticated users with
    the wrong role receive HTTP 403.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return login_required(wrapper)

    return decorator


login_required_any = login_required  # any authenticated role (object checks happen in the view)
admin_required = role_required("admin")
teacher_required = role_required("teacher")
student_required = role_required("student")
