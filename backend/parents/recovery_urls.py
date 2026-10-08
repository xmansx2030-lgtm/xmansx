from django.urls import path

from parents import recovery_api as api

urlpatterns = [
    path(
        "staff/parents/students/<int:student_id>/recovery/", api.SchoolRecoveryIntakeView.as_view()
    ),
    path("staff/parents/recovery-cases/", api.SchoolRecoveryListView.as_view()),
    path(
        "staff/parents/recovery-cases/<uuid:case_id>/cancel/",
        api.SchoolRecoveryCancelView.as_view(),
    ),
    path("identity-review/parent-recovery/", api.CentralRecoveryListView.as_view()),
    path(
        "identity-review/parent-recovery/<uuid:case_id>/", api.CentralRecoveryDetailView.as_view()
    ),
    path(
        "identity-review/parent-recovery/<uuid:case_id>/references/",
        api.CentralRecoveryEvidenceView.as_view(),
    ),
    path(
        "identity-review/parent-recovery/<uuid:case_id>/references/<int:evidence_id>/revoke/",
        api.CentralRecoveryEvidenceRevokeView.as_view(),
    ),
    path(
        "identity-review/parent-recovery/<uuid:case_id>/review/",
        api.CentralRecoveryReviewView.as_view(),
    ),
    path(
        "identity-review/parent-recovery/<uuid:case_id>/execute/",
        api.CentralRecoveryExecuteView.as_view(),
    ),
]
