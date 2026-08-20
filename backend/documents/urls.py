from django.urls import path

from documents.api import views

urlpatterns = [
    path("documents/", views.DocumentsView.as_view()),
    path("documents/preview/", views.DocumentPreviewView.as_view()),
    path("documents/generate/", views.DocumentGenerateView.as_view()),
    path("documents/<int:document_id>/download/", views.DocumentDownloadView.as_view()),
    path("documents/<int:document_id>/retry/", views.DocumentRetryView.as_view()),
    path("documents/<int:document_id>/void/", views.DocumentVoidView.as_view()),
    path("documents/<int:document_id>/", views.DocumentDetailView.as_view()),
]
