from django.urls import path

from operations.api import SystemHealthView

urlpatterns = [
    path("system-health/", SystemHealthView.as_view(), name="platform-system-health"),
]
