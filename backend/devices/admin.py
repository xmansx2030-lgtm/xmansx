from django.contrib import admin

from devices.models import (
    AttendanceDevice,
    DeviceBridgeInstallation,
    DeviceEvent,
    SchoolArrival,
    SchoolArrivalChange,
    StudentDeviceIdentity,
)


@admin.register(DeviceBridgeInstallation)
class BridgeAdmin(admin.ModelAdmin):
    list_display = ["installation_name", "school", "status", "last_seen_at"]
    list_filter = ["status", "school"]
    # ‏credential_hash لا يعرض ولا يعدل يدويًا
    exclude = ["credential_hash"]
    readonly_fields = ["installation_identifier", "last_seen_at"]


@admin.register(AttendanceDevice)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ["name", "school", "vendor", "status", "last_seen_at", "is_active"]
    list_filter = ["status", "school", "vendor"]
    exclude = ["connection_secret_encrypted"]  # السر لا يظهر حتى في Admin


@admin.register(StudentDeviceIdentity)
class IdentityAdmin(admin.ModelAdmin):
    list_display = ["device", "external_user_id", "student", "status", "school"]
    list_filter = ["status", "school"]


@admin.register(DeviceEvent)
class DeviceEventAdmin(admin.ModelAdmin):
    list_display = ["device", "external_user_id", "occurred_at", "processing_status"]
    list_filter = ["processing_status", "school"]
    readonly_fields = [f.name for f in DeviceEvent._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(SchoolArrival)
class ArrivalAdmin(admin.ModelAdmin):
    list_display = [
        "student", "attendance_date", "status", "counted_late_minutes", "source", "school",
    ]
    list_filter = ["status", "source", "school"]
    readonly_fields = [f.name for f in SchoolArrival._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(SchoolArrivalChange)
class ArrivalChangeAdmin(admin.ModelAdmin):
    """سجل تاريخي — قراءة فقط."""

    list_display = ["arrival", "previous_arrival_time", "new_arrival_time", "changed_at"]
    list_filter = ["school"]
    readonly_fields = [f.name for f in SchoolArrivalChange._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
