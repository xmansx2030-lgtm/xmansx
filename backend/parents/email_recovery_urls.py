from django.urls import path

from parents.email_recovery_api import (
    ParentPasswordRecoveryCheckView,
    ParentPasswordRecoveryCompleteView,
    ParentPasswordRecoveryView,
    RecoveryEmailResendView,
    RecoveryEmailVerifyCheckView,
    RecoveryEmailVerifyView,
    RecoveryEmailView,
)

urlpatterns = [
    path("parent/recovery-email/", RecoveryEmailView.as_view(), name="parent-recovery-email"),
    path("parent/recovery-email/resend/", RecoveryEmailResendView.as_view()),
    path("parent/recovery-email/verify/check/", RecoveryEmailVerifyCheckView.as_view()),
    path("parent/recovery-email/verify/", RecoveryEmailVerifyView.as_view()),
    path("auth/parent-password-recovery/", ParentPasswordRecoveryView.as_view()),
    path("auth/parent-password-recovery/check/", ParentPasswordRecoveryCheckView.as_view()),
    path("auth/parent-password-recovery/complete/", ParentPasswordRecoveryCompleteView.as_view()),
]
