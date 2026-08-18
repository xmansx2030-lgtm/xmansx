from django.urls import path

from students.api import views

urlpatterns = [
    path("students/", views.StudentListView.as_view()),
    path("students/<int:student_id>/", views.StudentDetailView.as_view()),
    path("grades/", views.GradeListView.as_view()),
    path("sections/", views.SectionListView.as_view()),
    path("student-imports/", views.ImportUploadView.as_view()),
    path("student-imports/<int:job_id>/", views.ImportJobView.as_view()),
    path("student-imports/<int:job_id>/process/", views.ImportProcessView.as_view()),
    path("student-imports/<int:job_id>/preview/", views.ImportPreviewView.as_view()),
    path("student-imports/<int:job_id>/commit/", views.ImportCommitView.as_view()),
    path("student-imports/<int:job_id>/cancel/", views.ImportCancelView.as_view()),
]
