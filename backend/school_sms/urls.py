from django.urls import path

from school_sms.api import (
    AbsenceSmsPreviewView,
    AbsenceSmsSendView,
    SchoolSmsIntegrationView,
    StudentSmsHistoryView,
)

urlpatterns = [
    path("sms/integration/", SchoolSmsIntegrationView.as_view()),
    path("sms/absences/preview/", AbsenceSmsPreviewView.as_view()),
    path("sms/absences/send/", AbsenceSmsSendView.as_view()),
    path("sms/students/<int:student_id>/history/", StudentSmsHistoryView.as_view()),
]
