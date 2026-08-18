from django.urls import path

from accounts.api.views import ActiveSchoolView

urlpatterns = [
    path("active-school/", ActiveSchoolView.as_view(), name="session-active-school"),
]
