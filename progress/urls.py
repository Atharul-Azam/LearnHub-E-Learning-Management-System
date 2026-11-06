from django.urls import path

from . import views

app_name = "progress"

urlpatterns = [
    path("my-courses/<int:pk>/progress/", views.course_progress, name="course_progress"),
]
