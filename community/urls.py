from django.urls import path

from . import views

app_name = "community"

urlpatterns = [
    path("my-courses/<int:pk>/community/", views.student_course, name="student_course"),
    path("teacher/courses/<int:pk>/community/", views.teacher_course, name="teacher_course"),
    path("community/course/<int:pk>/post/", views.post_create, name="post_create"),
    path("community/post/<int:pk>/edit/", views.post_edit, name="post_edit"),
    path("community/post/<int:pk>/delete/", views.post_delete, name="post_delete"),
    path("teacher/courses/<int:pk>/announce/", views.announcement_create, name="announcement_create"),
    path("teacher/announcements/<int:pk>/delete/", views.announcement_delete, name="announcement_delete"),
]
