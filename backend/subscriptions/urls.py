from django.urls import path

from subscriptions.api import school_views, views

urlpatterns = [
    path("platform/overview/", views.PlatformOverviewView.as_view()),
    path("platform/plans/", views.PlanListView.as_view()),
    path("platform/plans/<int:plan_id>/", views.PlanDetailView.as_view()),
    path("platform/schools/", views.SchoolListView.as_view()),
    path("platform/schools/<int:school_id>/", views.SchoolDetailView.as_view()),
    path("platform/schools/<int:school_id>/usage/", views.SchoolUsageView.as_view()),
    path("platform/schools/<int:school_id>/subscription/", views.SubscriptionView.as_view()),
    path(
        "platform/schools/<int:school_id>/subscription/events/",
        views.SubscriptionEventsView.as_view(),
    ),
    path(
        "platform/schools/<int:school_id>/subscription/plan-preview/",
        views.PlanChangePreviewView.as_view(),
    ),
    path(
        "platform/schools/<int:school_id>/entitlements/",
        views.EntitlementOverrideView.as_view(),
    ),
    path(
        "platform/schools/<int:school_id>/subscription/<str:action>/",
        views.SubscriptionActionView.as_view(),
    ),
    # جانب المدرسة: قراءة فقط
    path("school/subscription/", school_views.SchoolSubscriptionView.as_view()),
]
