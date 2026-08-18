from django.urls import path

from academics.api import views

urlpatterns = [
    path("academic-years/", views.AcademicYearListCreateView.as_view()),
    path("academic-years/<int:year_id>/", views.AcademicYearDetailView.as_view()),
    path("academic-years/<int:year_id>/semesters/", views.SemesterListCreateView.as_view()),
    path(
        "academic-years/<int:year_id>/<str:action>/",
        views.AcademicYearActionView.as_view(),
    ),
    path("semesters/<int:semester_id>/", views.SemesterDetailView.as_view()),
    path("semesters/<int:semester_id>/activate/", views.SemesterActivateView.as_view()),
    path("bell-schedules/", views.BellScheduleListCreateView.as_view()),
    path("bell-schedules/<int:schedule_id>/", views.BellScheduleDetailView.as_view()),
    path("bell-schedules/<int:schedule_id>/archive/", views.BellScheduleArchiveView.as_view()),
    path("bell-schedules/<int:schedule_id>/periods/", views.BellSchedulePeriodsView.as_view()),
    path("week-days/", views.WeekDaysView.as_view()),
]
