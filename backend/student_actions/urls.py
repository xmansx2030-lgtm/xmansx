from django.urls import path

from student_actions.api import views

urlpatterns = [
    path("student-actions/", views.StudentActionsView.as_view()),
    path("student-actions/<int:action_id>/cancel/", views.StudentActionCancelView.as_view()),
    path("student-actions/<int:action_id>/", views.StudentActionDetailView.as_view()),
]
