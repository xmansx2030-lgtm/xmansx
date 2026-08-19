from django.urls import path

from attendance.api import views

urlpatterns = [
    path("attendance/current-period/", views.CurrentPeriodView.as_view()),
    path("attendance/sections/", views.AttendanceSectionsView.as_view()),
    path("attendance/sessions/start/", views.StartSessionView.as_view()),
    path("attendance/sessions/<int:session_id>/", views.SessionDetailView.as_view()),
    path(
        "attendance/sessions/<int:session_id>/submit/",
        views.SubmitSessionView.as_view(),
    ),
    path("attendance/qr/resolve/", views.QrResolveView.as_view()),
    # GET = عرض/توليد أول مرة، POST = تجديد (يبطل القديم)
    path("sections/<int:section_id>/qr/", views.SectionQrView.as_view()),
]
