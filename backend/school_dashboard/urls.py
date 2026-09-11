from django.urls import path

from school_dashboard.api import views

urlpatterns = [
    path("dashboard/overview/", views.DashboardOverviewView.as_view()),
    path("dashboard/today/", views.DashboardTodayView.as_view()),
    path("dashboard/attendance-trend/", views.DashboardTrendView.as_view()),
    path("dashboard/sections/", views.DashboardSectionsView.as_view()),
    path("dashboard/attention/", views.DashboardAttentionView.as_view()),
    path("reports/absence/", views.AttendanceReportView.as_view()),
    path("reports/lateness/", views.LatenessReportView.as_view()),
    path("reports/referrals/", views.ReferralsReportView.as_view()),
]
