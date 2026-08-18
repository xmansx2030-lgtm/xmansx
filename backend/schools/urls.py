from django.urls import path

from schools import api

urlpatterns = [
    path("settings/", api.SchoolSettingsView.as_view(), name="school-settings"),
    path("settings/logo/", api.SchoolLogoView.as_view(), name="school-logo"),
]
