"""Navigation: the active tab is computed on the server from the matched URL name,
so it is correct after a refresh, a direct link or a nested page (no JavaScript state)."""
from django.urls import reverse

# (label, url name, view-name prefixes that make the tab active)
NAV = {
    "admin": [
        ("Dashboard", "dashboards:home", ("dashboards:",)),
        ("Teacher Requests", "accounts:teacher_requests", ("accounts:teacher_request", "accounts:approve", "accounts:reject")),
        ("Users", "accounts:user_list", ("accounts:user_", "accounts:activate", "accounts:deactivate", "accounts:remove")),
        ("Courses", "courses:admin_list", ("courses:admin_",)),
    ],
    "teacher": [
        ("Dashboard", "dashboards:home", ("dashboards:teacher", "dashboards:home")),
        (
            "My Courses",
            "courses:teacher_list",
            ("courses:teacher_list", "courses:teacher_detail", "courses:teacher_edit", "courses:teacher_delete",
             "courses:teacher_students", "courses:teacher_sharing", "courses:student_revoke",
             "materials:", "assignments:", "community:teacher_course", "community:announcement",
             "community:post_"),
        ),
        ("Requests", "courses:teacher_requests_all", ("courses:teacher_requests", "courses:request_")),
        ("Analytics", "dashboards:analytics", ("dashboards:analytics",)),
        ("Create Course", "courses:teacher_create", ("courses:teacher_create",)),
    ],
    "student": [
        ("Dashboard", "dashboards:home", ("dashboards:",)),
        ("Browse Courses", "courses:browse", ("courses:browse", "courses:detail", "courses:join", "courses:enroll")),
        (
            "My Courses",
            "courses:my_courses",
            ("courses:my_courses", "courses:open_course", "progress:", "assignments:student", "assignments:attachment",
             "assignments:submission", "materials:file", "community:student_course", "community:post_"),
        ),
        ("Favourites", "courses:favourites", ("courses:favourites",)),
    ],
}


def navigation(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    match = getattr(request, "resolver_match", None)
    current = match.view_name if match else ""
    items, chosen = [], False
    for label, name, prefixes in NAV.get(user.role, []):
        active = (not chosen) and any(current.startswith(p) for p in prefixes)
        # The first matching tab wins, so a nested page highlights exactly one item.
        chosen = chosen or active
        items.append({"label": label, "url": reverse(name), "active": active})
    sections = [
        ("account", "Account information", reverse("accounts:settings")),
        ("profile", "Edit profile & picture", reverse("accounts:settings_profile")),
        ("password", "Change password", reverse("accounts:settings_password")),
        ("notifications", "Notification preferences", reverse("accounts:settings_notifications")),
        ("appearance", "Appearance", reverse("accounts:settings_appearance")),
        ("security", "Account security", reverse("accounts:settings_security")),
        ("delete", "Delete account", reverse("accounts:settings_delete")),
    ]
    section = "settings" if current.startswith("accounts:settings") or current == "accounts:profile" else ""
    return {"nav_items": items, "nav_section": section, "settings_sections": sections}
