from django.urls import path

from . import views

app_name = "dashboards"

urlpatterns = [
    path("dashboard/", views.home, name="home"),
    path("dashboard/admin/", views.admin_dashboard, name="admin"),
    path("dashboard/teacher/", views.teacher_dashboard, name="teacher"),
    path("dashboard/student/", views.student_dashboard, name="student"),
]
