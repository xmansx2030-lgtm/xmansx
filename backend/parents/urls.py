from django.urls import include, path

from parents import api

urlpatterns = [
    path("parent/registration/<uuid:token>/", api.RegistrationView.as_view()),
    path("parent/registration/status/", api.ReceiptView.as_view()),
    path("parent/activation/check/", api.ActivationCheckView.as_view()),
    path("parent/activation/", api.ActivationView.as_view()),
    path("parent/account/password/", api.ParentPasswordView.as_view()),
    path("parent/children/", api.ChildrenView.as_view()),
    path("parent/children/<int:relation_id>/", api.ChildView.as_view()),
    path("parent/children/<int:relation_id>/history/", api.HistoryView.as_view()),
    path("staff/parents/settings/", api.ParentSettingsView.as_view()),
    path("staff/parents/registrations/", api.StaffRegistrationListView.as_view()),
    path("staff/parents/registrations/<int:request_id>/", api.StaffRegistrationView.as_view()),
    path(
        "staff/parents/registrations/<int:request_id>/decision/",
        api.StaffRegistrationDecisionView.as_view(),
    ),
    path(
        "staff/parents/registrations/<int:request_id>/activation/",
        api.StaffActivationReissueView.as_view(),
    ),
    path("staff/parents/relations/", api.StaffRelationsView.as_view()),
    path(
        "staff/parents/relations/<int:relation_id>/decision/",
        api.StaffRelationDecisionView.as_view(),
    ),
    path("staff/parents/", include("parents.contact_urls")),
    path("", include("parents.request_urls")),
]
