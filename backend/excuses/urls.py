from django.urls import path

from excuses.api import views

urlpatterns = [
    # القائمة والإنشاء — قراءة: مدير/وكيل/مرشد؛ كتابة: مدير/وكيل
    path("excuses/", views.ExcuseListCreateView.as_view()),
    path("excuses/kpis/", views.ExcuseKpisView.as_view()),
    path("excuses/<int:excuse_id>/", views.ExcuseDetailView.as_view()),
    # إجراءات دورة الحياة — endpoints منفصلة (لا PATCH لحالة الاعتماد)
    path("excuses/<int:excuse_id>/preview/", views.ExcusePreviewView.as_view()),
    path("excuses/<int:excuse_id>/approve/", views.ExcuseApproveView.as_view()),
    path("excuses/<int:excuse_id>/reject/", views.ExcuseRejectView.as_view()),
    path("excuses/<int:excuse_id>/cancel/", views.ExcuseCancelView.as_view()),
    # المرفقات — التنزيل مصرح للمدير/الوكيل فقط
    path("excuses/<int:excuse_id>/attachments/", views.ExcuseAttachmentsView.as_view()),
    path(
        "excuses/<int:excuse_id>/attachments/<int:attachment_id>/",
        views.ExcuseAttachmentDetailView.as_view(),
    ),
]
