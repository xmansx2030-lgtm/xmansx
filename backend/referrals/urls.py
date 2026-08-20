from django.urls import path

from referrals.api import views

urlpatterns = [
    # المسارات المحددة قبل <int:...> (نفس ترتيب بقية التطبيقات)
    path("referrals/", views.ReferralListCreateView.as_view()),
    path("referrals/mine/", views.MyReferralsView.as_view()),
    path("referrals/kpis/", views.ReferralKpisView.as_view()),
    path("referrals/options/", views.ReferralOptionsView.as_view()),
    path("referrals/counselors/", views.CounselorListView.as_view()),
    # ملاحظة على الحالة المفتوحة لـ(طالب، فئة) — بلا تمرير معرف إحالة
    path("referrals/contribute/", views.ContributeToOpenCaseView.as_view()),
    path("referrals/<int:referral_id>/", views.ReferralDetailView.as_view()),
    path("referrals/<int:referral_id>/assign/", views.ReferralAssignView.as_view()),
    path(
        "referrals/<int:referral_id>/acknowledge/",
        views.ReferralAcknowledgeView.as_view(),
    ),
    path("referrals/<int:referral_id>/close/", views.ReferralCloseView.as_view()),
    path("referrals/<int:referral_id>/cancel/", views.ReferralCancelView.as_view()),
    path(
        "referrals/<int:referral_id>/contributions/",
        views.ReferralContributionsView.as_view(),
    ),
    path("students/<int:student_id>/referrals/", views.StudentReferralsView.as_view()),
]
