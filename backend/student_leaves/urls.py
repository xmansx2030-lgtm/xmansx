from django.urls import path

from student_leaves.api import views

urlpatterns = [
    path("student-leaves/", views.StudentLeaveListView.as_view()),
    path(
        "student-leaves/<int:leave_id>/cancel/",
        views.StudentLeaveCancelView.as_view(),
    ),
    path("gate/student-leaves/", views.GateStudentLeaveListView.as_view()),
    path(
        "gate/student-leaves/<int:leave_id>/release/",
        views.GateStudentLeaveReleaseView.as_view(),
    ),
]
