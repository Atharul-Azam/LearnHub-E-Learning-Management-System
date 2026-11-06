from django.urls import path

from . import views

app_name = "materials"

urlpatterns = [
    path("teacher/courses/<int:course_pk>/materials/add/", views.material_add, name="add"),
    path("teacher/materials/<int:pk>/edit/", views.material_edit, name="edit"),
    path("teacher/materials/<int:pk>/delete/", views.material_delete, name="delete"),
    path("files/materials/<int:pk>/", views.material_file, name="file"),
]
