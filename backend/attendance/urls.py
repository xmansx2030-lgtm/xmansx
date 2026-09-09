from django.urls import path

from attendance.api import views

urlpatterns = [
    path("attendance/current-period/", views.CurrentPeriodView.as_view()),
    path("attendance/sections/", views.AttendanceSectionsView.as_view()),
    path(
        "attendance/sections/<int:section_id>/preview/",
        views.AttendanceSectionPreviewView.as_view(),
    ),
    path("attendance/sessions/start/", views.StartSessionView.as_view()),
    path("attendance/sessions/<int:session_id>/", views.SessionDetailView.as_view()),
    path(
        "attendance/sessions/<int:session_id>/submit/",
        views.SubmitSessionView.as_view(),
    ),
    path("attendance/qr/resolve/", views.QrResolveView.as_view()),
    # لوحة المتابعة (م7) — لا school_id في المسار: request.school من الجلسة حصرًا
    path("attendance/monitoring/current/", views.MonitoringCurrentView.as_view()),
    # التحليلات (م8) — مدير/وكيل فقط، بلا PII طلاب
    path("attendance/analytics/period/", views.PeriodAnalyticsView.as_view()),
    path("attendance/analytics/multi-period/", views.MultiPeriodAnalyticsView.as_view()),
    path("attendance/analytics/daily/", views.DailyAnalyticsView.as_view()),
    # GET = عرض/توليد أول مرة، POST = تجديد (يبطل القديم)
    path("sections/<int:section_id>/qr/", views.SectionQrView.as_view()),
]
