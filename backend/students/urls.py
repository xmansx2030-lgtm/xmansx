from django.urls import path

from students.api import lifecycle_views, views

urlpatterns = [
    path("students/search/", views.StudentSearchView.as_view()),
    path("students/", views.StudentListView.as_view()),
    path("students/inactive/", lifecycle_views.InactiveStudentsView.as_view()),
    path("students/bulk-status/", lifecycle_views.BulkStatusView.as_view()),
    path("students/<int:student_id>/status/", lifecycle_views.StudentStatusView.as_view()),
    path("students/<int:student_id>/purge/", lifecycle_views.StudentPurgeView.as_view()),
    path("student-purges/preview/", lifecycle_views.PurgePreviewView.as_view()),
    path("student-purges/", lifecycle_views.PurgeCreateView.as_view()),
    path("student-purges/<int:job_id>/", lifecycle_views.PurgeJobView.as_view()),
    path(
        "students/<int:student_id>/attendance-profile/",
        views.StudentAttendanceProfileView.as_view(),
    ),
    path(
        "students/<int:student_id>/attendance-days/",
        views.StudentAttendanceDaysView.as_view(),
    ),
    path(
        "students/<int:student_id>/attendance-days/<str:attendance_date>/",
        views.StudentAttendanceDayDetailView.as_view(),
    ),
    path(
        "students/<int:student_id>/attendance-period-absences/",
        views.StudentAttendanceAbsencesView.as_view(),
    ),
    path(
        "students/<int:student_id>/attendance-period-lates/",
        views.StudentAttendanceLatesView.as_view(),
    ),
    path(
        "students/<int:student_id>/attendance-changes/",
        views.StudentAttendanceChangesView.as_view(),
    ),
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
