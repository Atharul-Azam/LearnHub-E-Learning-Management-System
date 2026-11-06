from django.urls import path

from . import views

app_name = "assignments"

urlpatterns = [
    # UC10 - teacher
    path("teacher/courses/<int:course_pk>/assignments/add/", views.assignment_add, name="teacher_add"),
    path("teacher/assignments/<int:pk>/", views.assignment_detail, name="teacher_detail"),
    path("teacher/assignments/<int:pk>/edit/", views.assignment_edit, name="teacher_edit"),
    path("teacher/assignments/<int:pk>/delete/", views.assignment_delete, name="teacher_delete"),
    # UC12 - teacher reviews a submission
    path("teacher/submissions/<int:pk>/", views.review_submission, name="review"),
    # UC16 - student
    path("assignments/<int:pk>/", views.student_assignment, name="student_detail"),
    # Controlled file access
    path("files/assignments/<int:pk>/", views.attachment_file, name="attachment"),
    path("files/submissions/<int:pk>/", views.submission_file, name="submission_file"),
]
