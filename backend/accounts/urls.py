from django.urls import path

from accounts.api import views

urlpatterns = [
    path("csrf/", views.CsrfView.as_view(), name="auth-csrf"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.MeView.as_view(), name="auth-me"),
    path("schools/", views.MySchoolsView.as_view(), name="auth-schools"),
    path(
        "change-initial-password/",
        views.ChangeInitialPasswordView.as_view(),
        name="auth-change-initial-password",
    ),
    path("invitations/", views.InvitationsView.as_view(), name="auth-invitations"),
    path(
        "invitations/<int:invitation_id>/accept/",
        views.InvitationAcceptView.as_view(),
        name="auth-invitation-accept",
    ),
    path(
        "invitations/<int:invitation_id>/decline/",
        views.InvitationDeclineView.as_view(),
        name="auth-invitation-decline",
    ),
]
