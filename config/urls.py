from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("", core_views.home, name="home"),
    path("", include("accounts.urls")),
    path("", include("dashboards.urls")),
    path("", include("courses.urls")),
    path("", include("materials.urls")),
    path("", include("assignments.urls")),
    path("", include("progress.urls")),
]

handler403 = "core.views.permission_denied"
handler404 = "core.views.page_not_found"
handler500 = "core.views.server_error"
