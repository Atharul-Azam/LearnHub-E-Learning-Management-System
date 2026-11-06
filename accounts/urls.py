from django.urls import path

from . import views, views_admin

app_name = "accounts"

urlpatterns = [
    # UC1 / UC2
    path("accounts/register/", views.register, name="register"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/logout/", views.logout_view, name="logout"),
    # UC3 - teacher requests (administrator)
    path("manage/teacher-requests/", views_admin.teacher_requests, name="teacher_requests"),
    path("manage/teacher-requests/<int:pk>/", views_admin.teacher_request_detail, name="teacher_request_detail"),
    path("manage/teacher-requests/<int:pk>/approve/", views_admin.approve_teacher, name="approve_teacher"),
    path("manage/teacher-requests/<int:pk>/reject/", views_admin.reject_teacher, name="reject_teacher"),
    # UC4 - user accounts (administrator)
    path("manage/users/", views_admin.user_list, name="user_list"),
    path("manage/users/<int:pk>/", views_admin.user_detail, name="user_detail"),
    path("manage/users/<int:pk>/activate/", views_admin.activate_user, name="activate_user"),
    path("manage/users/<int:pk>/deactivate/", views_admin.deactivate_user, name="deactivate_user"),
    path("manage/users/<int:pk>/remove/", views_admin.remove_user, name="remove_user"),
]
