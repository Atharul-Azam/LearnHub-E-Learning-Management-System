from django.urls import path

from . import views_admin, views_student, views_teacher

app_name = "courses"

urlpatterns = [
    # UC5 - administrator
    path("manage/courses/", views_admin.admin_list, name="admin_list"),
    path("manage/courses/<int:pk>/", views_admin.admin_detail, name="admin_detail"),
    path("manage/courses/<int:pk>/hide/", views_admin.admin_hide, name="admin_hide"),
    path("manage/courses/<int:pk>/publish/", views_admin.admin_publish, name="admin_publish"),
    path("manage/courses/<int:pk>/remove/", views_admin.admin_remove, name="admin_remove"),
    # UC7, UC8, UC11 - teacher
    path("teacher/courses/", views_teacher.teacher_list, name="teacher_list"),
    path("teacher/courses/new/", views_teacher.teacher_create, name="teacher_create"),
    path("teacher/courses/<int:pk>/", views_teacher.teacher_detail, name="teacher_detail"),
    path("teacher/courses/<int:pk>/edit/", views_teacher.teacher_edit, name="teacher_edit"),
    path("teacher/courses/<int:pk>/delete/", views_teacher.teacher_delete, name="teacher_delete"),
    path("teacher/courses/<int:pk>/students/", views_teacher.teacher_students, name="teacher_students"),
    # UC13, UC14 and enrolled-course pages - student
    path("courses/", views_student.browse, name="browse"),
    path("courses/<int:pk>/", views_student.detail, name="detail"),
    path("courses/<int:pk>/enroll/", views_student.enroll, name="enroll"),
    path("my-courses/", views_student.my_courses, name="my_courses"),
    path("my-courses/<int:pk>/", views_student.open_course, name="open_course"),
    # Controlled thumbnail access
    path("files/thumbnails/<int:pk>/", views_student.thumbnail, name="thumbnail"),
]
