from django.urls import path

from devices.api import views

urlpatterns = [
    # إدارة (مدير فقط)
    path("device-bridges/", views.BridgesView.as_view()),
    path("device-bridges/<int:bridge_id>/rotate/", views.BridgeRotateView.as_view()),
    path("devices/", views.DevicesView.as_view()),
    path("devices/<int:device_id>/", views.DeviceDetailView.as_view()),
    path("devices/<int:device_id>/test-connection/", views.DeviceTestView.as_view()),
    path("devices/<int:device_id>/roster-sync/analyze/", views.DeviceRosterAnalyzeView.as_view()),
    path("device-roster-syncs/<int:job_id>/", views.DeviceRosterJobView.as_view()),
    path("device-roster-syncs/<int:job_id>/items/", views.DeviceRosterItemsView.as_view()),
    path("device-roster-syncs/<int:job_id>/approve/", views.DeviceRosterApproveView.as_view()),
    path("device-roster-syncs/<int:job_id>/retry/", views.DeviceRosterRetryView.as_view()),
    path("device-identities/", views.IdentitiesView.as_view()),
    path("device-identities/<int:identity_id>/map/", views.IdentityMapView.as_view()),
    path("device-identities/<int:identity_id>/unmap/", views.IdentityUnmapView.as_view()),
    # التأخر الصباحي (الإدارة + المعلم المكلّف)
    path("morning/summary/", views.MorningSummaryView.as_view()),
    path("morning/students/search/", views.MorningStudentSearchView.as_view()),
    path("morning/late/", views.MorningLateListView.as_view()),
    path(
        "morning/students/<int:student_id>/history/",
        views.StudentLateHistoryView.as_view(),
    ),
    path("morning/arrivals/", views.ManualArrivalView.as_view()),
    path("morning/arrivals/<int:arrival_id>/correct/", views.ArrivalCorrectView.as_view()),
    # الجسر (رمز اعتماد — هوية المدرسة منه حصرًا)
    path("bridge/events/batch/", views.BridgeEventsBatchView.as_view()),
    path("bridge/heartbeat/", views.BridgeHeartbeatView.as_view()),
    path("bridge/devices/", views.BridgeDevicesView.as_view()),
    path("bridge/roster/read/", views.BridgeRosterReadView.as_view()),
    path("bridge/roster/command-result/", views.BridgeRosterCommandResultView.as_view()),
]
