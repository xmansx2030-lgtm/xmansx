from django.urls import path

from parents.contact_api import (
    ContactReviewListView,
    ContactReviewResolveView,
    GlobalMobileChangeListView,
    GlobalMobileChangeView,
    RecipientBlockCreateView,
    RecipientBlockListView,
    RecipientBlockResolveView,
    StudentContactView,
)

urlpatterns = [
    path("contact-reviews/", ContactReviewListView.as_view()),
    path("contact-reviews/<int:review_id>/resolve/", ContactReviewResolveView.as_view()),
    path("students/<int:student_id>/contact/", StudentContactView.as_view()),
    path("recipient-blocks/", RecipientBlockListView.as_view()),
    path("students/<int:student_id>/recipient-blocks/", RecipientBlockCreateView.as_view()),
    path("recipient-blocks/<int:block_id>/resolve/", RecipientBlockResolveView.as_view()),
    path("global-mobile-changes/", GlobalMobileChangeListView.as_view()),
    path("students/<int:student_id>/global-mobile-change/", GlobalMobileChangeView.as_view()),
]
