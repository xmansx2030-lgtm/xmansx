from django.urls import path

from common import health

urlpatterns = [
    path("health/", health.health, name="health"),
    path("readiness/", health.readiness, name="readiness"),
]
