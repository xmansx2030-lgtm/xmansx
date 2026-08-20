from django.urls import path

from counseling.api import views

urlpatterns = [
    # الحالات — المسارات المحددة قبل <int:...>
    path("counselor/dashboard/", views.CounselorDashboardView.as_view()),
    path("counselor/cases/", views.CaseListView.as_view()),
    path("counselor/teachers/", views.CaseTeachersView.as_view()),
    path("counselor/cases/<int:case_id>/", views.CaseDetailView.as_view()),
    path("counselor/cases/<int:case_id>/status/", views.CaseStatusView.as_view()),
    path("counselor/cases/<int:case_id>/close/", views.CaseCloseView.as_view()),
    path("counselor/cases/<int:case_id>/reopen/", views.CaseReopenView.as_view()),
    path("counselor/cases/<int:case_id>/reassign/", views.CaseReassignView.as_view()),
    path("counselor/cases/<int:case_id>/sessions/", views.CaseSessionsView.as_view()),
    path("counselor/cases/<int:case_id>/plans/", views.CasePlansView.as_view()),
    path(
        "counselor/cases/<int:case_id>/teacher-requests/",
        views.CaseTeacherRequestsView.as_view(),
    ),
    path("counselor/cases/<int:case_id>/timeline/", views.CaseTimelineView.as_view()),
    path("counselor/sessions/<int:session_id>/void/", views.SessionVoidView.as_view()),
    path("counselor/plans/<int:plan_id>/status/", views.PlanStatusView.as_view()),
    path("counselor/plans/<int:plan_id>/goals/", views.PlanGoalsView.as_view()),
    path("counselor/plans/<int:plan_id>/activities/", views.PlanActivitiesView.as_view()),
    path("counselor/goals/<int:goal_id>/", views.GoalStatusView.as_view()),
    path(
        "counselor/activities/<int:activity_id>/complete/",
        views.ActivityCompleteView.as_view(),
    ),
    # فتح الملف من الإحالة (يبقى ضمن مساحة الإحالات لأنه فعل عليها)
    path("referrals/<int:referral_id>/open-case/", views.ReferralOpenCaseView.as_view()),
    # صندوق المعلم
    path("teacher/follow-up-requests/", views.TeacherFollowUpListView.as_view()),
    path(
        "teacher/follow-up-requests/<int:request_id>/respond/",
        views.TeacherFollowUpRespondView.as_view(),
    ),
    # ملخص ملف الطالب
    path("students/<int:student_id>/counseling/", views.StudentCounselingView.as_view()),
]
