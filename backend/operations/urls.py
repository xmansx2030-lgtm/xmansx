from django.urls import path

from academics.api.ministry import PlatformMinistryCalendarView, PlatformSchoolCalendarScopeView
from operations.api import SystemHealthView

urlpatterns = [
    path("ministry-calendar/", PlatformMinistryCalendarView.as_view()),
    path("schools/<int:school_id>/calendar-scope/", PlatformSchoolCalendarScopeView.as_view()),
    path("system-health/", SystemHealthView.as_view(), name="platform-system-health"),
]
