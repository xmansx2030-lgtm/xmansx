from django.urls import path

from platform_team import api

urlpatterns = [
    path("account/", api.PlatformAccountView.as_view(), name="platform-account"),
    path(
        "account/change-password/",
        api.PlatformPasswordView.as_view(),
        name="platform-account-password",
    ),
    path("team/", api.PlatformTeamView.as_view(), name="platform-team"),
    path("team/<int:user_id>/", api.PlatformTeamMemberView.as_view(), name="platform-team-member"),
    path(
        "team/<int:user_id>/<str:action>/",
        api.PlatformTeamMemberActionView.as_view(),
        name="platform-team-member-action",
    ),
]
