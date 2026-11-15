from django.urls import path

from . import views, views_admin, views_profile

app_name = "accounts"

urlpatterns = [
    # UC1 / UC2
    path("accounts/register/", views.register, name="register"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("accounts/verify/<uidb64>/<token>/", views.verify_email, name="verify_email"),
    path("accounts/resend-verification/", views.resend_verification, name="resend_verification"),
    # profile and settings (any signed-in user; every view acts only on request.user)
    path("profile/", views_profile.profile, name="profile"),
    path("settings/", views_profile.settings_home, name="settings"),
    path("settings/profile/", views_profile.settings_profile, name="settings_profile"),
    path("settings/password/", views_profile.settings_password, name="settings_password"),
    path("settings/notifications/", views_profile.settings_notifications, name="settings_notifications"),
    path("settings/appearance/", views_profile.settings_appearance, name="settings_appearance"),
    path("settings/security/", views_profile.settings_security, name="settings_security"),
    path("settings/security/sign-out-others/", views_profile.sign_out_other_devices, name="sign_out_others"),
    path("settings/delete/", views_profile.settings_delete, name="settings_delete"),
    path("files/avatars/<int:pk>/", views_profile.avatar_file, name="avatar"),
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
