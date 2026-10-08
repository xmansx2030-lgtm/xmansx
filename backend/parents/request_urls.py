from django.urls import path

from parents import request_api as views

urlpatterns = [
    path("parent/requests/", views.ParentRequestsView.as_view()),
    path("parent/notifications/", views.ParentNotificationsView.as_view()),
    path(
        "parent/notifications/<int:notification_id>/read/",
        views.ParentNotificationReadView.as_view(),
    ),
    path(
        "parent/notifications/<int:notification_id>/complete-action/",
        views.ParentNotificationCompleteView.as_view(),
    ),
    path("parent/children/<int:relation_id>/excuses/", views.ParentExcusesView.as_view()),
    path(
        "parent/children/<int:relation_id>/excuses/<int:request_id>/resubmit/",
        views.ParentExcuseResubmitView.as_view(),
    ),
    path(
        "parent/children/<int:relation_id>/excuses/<int:request_id>/cancel/",
        views.ParentExcuseCancelView.as_view(),
    ),
    path(
        "parent/children/<int:relation_id>/excuses/<int:request_id>/attachments/",
        views.ParentExcuseAttachmentsView.as_view(),
    ),
    path(
        "parent/children/<int:relation_id>/excuses/<int:request_id>/attachments/<int:attachment_id>/download/",
        views.ParentAttachmentDownloadView.as_view(),
    ),
    path("parent/children/<int:relation_id>/corrections/", views.ParentCorrectionsView.as_view()),
    path(
        "parent/children/<int:relation_id>/corrections/<int:request_id>/cancel/",
        views.ParentCorrectionCancelView.as_view(),
    ),
    path("parent/children/<int:relation_id>/warnings/", views.ParentWarningsView.as_view()),
    path(
        "parent/children/<int:relation_id>/warnings/<int:warning_id>/acknowledge/",
        views.ParentWarningAcknowledgeView.as_view(),
    ),
    path("parent/children/<int:relation_id>/publications/", views.ParentPublicationsView.as_view()),
    path(
        "parent/children/<int:relation_id>/publications/<int:publication_id>/download/",
        views.ParentPublicationDownloadView.as_view(),
    ),
    path(
        "parent/children/<int:relation_id>/publications/<int:publication_id>/acknowledge/",
        views.ParentPublicationAcknowledgeView.as_view(),
    ),
    path("staff/parents/requests/", views.StaffRequestsView.as_view()),
    path("staff/parents/acknowledgements/", views.StaffAcknowledgementsView.as_view()),
    path(
        "staff/parents/excuses/<int:request_id>/decision/", views.StaffExcuseDecisionView.as_view()
    ),
    path(
        "staff/parents/corrections/<int:request_id>/decision/",
        views.StaffCorrectionDecisionView.as_view(),
    ),
    path(
        "staff/parents/excuses/<int:request_id>/attachments/<int:attachment_id>/download/",
        views.StaffAttachmentDownloadView.as_view(),
    ),
    path("staff/parents/publications/", views.StaffPublicationsView.as_view()),
    path(
        "staff/parents/publications/<int:publication_id>/revoke/",
        views.StaffPublicationRevokeView.as_view(),
    ),
]
