from django.urls import path

from staff.api import views

urlpatterns = [
    path("staff/", views.StaffListView.as_view()),
    path("staff/<int:staff_id>/", views.StaffDetailView.as_view()),
    path("staff/<int:staff_id>/roles/", views.StaffRolesView.as_view()),
    path("staff/<int:staff_id>/roles/<str:role>/", views.StaffRoleDeleteView.as_view()),
    path("staff/<int:staff_id>/suspend/", views.StaffSuspendView.as_view()),
    path("staff/<int:staff_id>/activate/", views.StaffActivateView.as_view()),
    path("staff/<int:staff_id>/reinvite/", views.StaffReinviteView.as_view()),
    path("staff-imports/", views.StaffImportUploadView.as_view()),
    path("staff-imports/<int:job_id>/", views.StaffImportJobView.as_view()),
    path("staff-imports/<int:job_id>/process/", views.StaffImportProcessView.as_view()),
    path("staff-imports/<int:job_id>/preview/", views.StaffImportPreviewView.as_view()),
    path("staff-imports/<int:job_id>/commit/", views.StaffImportCommitView.as_view()),
    path("staff-imports/<int:job_id>/cancel/", views.StaffImportCancelView.as_view()),
]
