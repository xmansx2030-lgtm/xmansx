from django.urls import path

from student_warnings.api import views

urlpatterns = [
    path("warning-rules/", views.WarningRulesView.as_view()),
    path("warnings/eligibility/", views.WarningEligibilityView.as_view()),
    path(
        "warnings/eligibility/students/<int:student_id>/",
        views.StudentEligibilityView.as_view(),
    ),
    path("warnings/issue/", views.WarningIssueView.as_view()),
    path("warnings/<int:warning_id>/void/", views.WarningVoidView.as_view()),
    path("warnings/<int:warning_id>/", views.WarningDetailView.as_view()),
    path("warnings/", views.WarningsView.as_view()),
]
