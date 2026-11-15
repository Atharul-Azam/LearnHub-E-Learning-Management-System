from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("notifications/", views.notification_list, name="list"),
    path("notifications/<int:pk>/open/", views.notification_open, name="open"),
    path("notifications/read-all/", views.notification_read_all, name="read_all"),
]
