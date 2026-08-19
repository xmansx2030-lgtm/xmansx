"""‏Serializers أجهزة الحضور والصباحي — serializer-first (قاعدة OPENAPI.md).

قاعدة صلبة: أسرار الجهاز/الجسر لا تظهر في أي إخراج متصفح — إخراج الجسر الموثق فقط
يحمل سر اتصال الجهاز (يحتاجه للاتصال المحلي).
"""

from rest_framework import serializers

from devices.models import IdentityStatus, VerificationMethod

# ---- إدخال المتصفح ----


class BridgeCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)


class DeviceCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    vendor = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    model = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    serial_number = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    connection_type = serializers.CharField(max_length=20, required=False, default="TCP")
    local_ip = serializers.IPAddressField(required=False, allow_blank=True, default="")
    local_port = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=65535, default=None
    )
    connection_secret = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default="", write_only=True
    )


class DeviceUpdateSerializer(DeviceCreateSerializer):
    name = serializers.CharField(max_length=100, required=False)
    is_active = serializers.BooleanField(required=False)


class IdentityMapSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)


class ManualArrivalSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)
    date = serializers.DateField()
    arrival_time = serializers.TimeField()
    reason = serializers.CharField(max_length=300)


class ArrivalCorrectionSerializer(serializers.Serializer):
    arrival_time = serializers.TimeField()
    reason = serializers.CharField(max_length=300)


# ---- إخراج المتصفح ----


class BridgeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    installation_name = serializers.CharField()
    status = serializers.CharField()
    last_seen_at = serializers.DateTimeField(allow_null=True)
    is_online = serializers.BooleanField()


class BridgeCredentialSerializer(serializers.Serializer):
    bridge = BridgeSerializer()
    credential = serializers.CharField()  # يعرض مرة واحدة فقط — لا يخزن


class DeviceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    vendor = serializers.CharField()
    model = serializers.CharField()
    serial_number = serializers.CharField()
    connection_type = serializers.CharField()
    local_ip = serializers.CharField()
    local_port = serializers.IntegerField(allow_null=True)
    status = serializers.CharField()
    last_seen_at = serializers.DateTimeField(allow_null=True)
    last_successful_sync_at = serializers.DateTimeField(allow_null=True)
    is_active = serializers.BooleanField()
    unmatched_events = serializers.IntegerField()
    test_result = serializers.JSONField(allow_null=True)
    # ملاحظة: لا connection_secret هنا أبدًا


class IdentitySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    device_id = serializers.IntegerField()
    device_name = serializers.CharField()
    external_user_id = serializers.CharField()
    display_name = serializers.CharField()
    status = serializers.ChoiceField(choices=IdentityStatus.choices)
    student_id = serializers.IntegerField(allow_null=True)
    student_name = serializers.CharField(allow_null=True)


class MorningSummarySerializer(serializers.Serializer):
    date = serializers.DateField()
    arrived_total = serializers.IntegerField()
    on_time = serializers.IntegerField()
    late = serializers.IntegerField()
    late_minutes_total = serializers.IntegerField()
    unmatched_events = serializers.IntegerField()
    devices_total = serializers.IntegerField()
    devices_offline = serializers.IntegerField()


class LateStudentSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    full_name = serializers.CharField()
    grade_name = serializers.CharField()
    section_name = serializers.CharField()
    arrival_time = serializers.CharField()
    raw_late_minutes = serializers.IntegerField()
    counted_late_minutes = serializers.IntegerField()
    source = serializers.CharField()


class LateListSerializer(serializers.Serializer):
    date = serializers.DateField()
    total_late = serializers.IntegerField()
    students = LateStudentSerializer(many=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class LateHistoryEntrySerializer(serializers.Serializer):
    date = serializers.DateField()
    arrival_time = serializers.CharField()
    raw_late_minutes = serializers.IntegerField()
    counted_late_minutes = serializers.IntegerField()
    source = serializers.CharField()


class StudentLateHistorySerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    full_name = serializers.CharField()
    late_count = serializers.IntegerField()
    total_late_minutes = serializers.IntegerField()
    entries = LateHistoryEntrySerializer(many=True)


class ArrivalSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    attendance_date = serializers.DateField()
    arrival_time = serializers.CharField()
    status = serializers.CharField()
    raw_late_minutes = serializers.IntegerField()
    counted_late_minutes = serializers.IntegerField()
    source = serializers.CharField()


# ---- الجسر ----


class BridgeEventSerializer(serializers.Serializer):
    device_id = serializers.IntegerField()
    external_event_id = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    external_user_id = serializers.CharField(max_length=64)
    occurred_at = serializers.DateTimeField()
    verification_method = serializers.ChoiceField(
        choices=VerificationMethod.choices, default="UNKNOWN"
    )
    event_type = serializers.CharField(max_length=20, required=False, default="CHECK_IN")


class BridgeBatchSerializer(serializers.Serializer):
    events = BridgeEventSerializer(many=True, max_length=1000)


class BridgeBatchResultSerializer(serializers.Serializer):
    results = serializers.ListField(child=serializers.DictField())


class BridgeHeartbeatDeviceSerializer(serializers.Serializer):
    device_id = serializers.IntegerField()
    reachable = serializers.BooleanField()
    test_result = serializers.DictField(required=False, allow_null=True, default=None)


class BridgeHeartbeatSerializer(serializers.Serializer):
    devices = BridgeHeartbeatDeviceSerializer(many=True, required=False, default=list)


class BridgeDeviceConfigSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    vendor = serializers.CharField()
    connection_type = serializers.CharField()
    local_ip = serializers.CharField()
    local_port = serializers.IntegerField(allow_null=True)
    connection_secret = serializers.CharField(allow_blank=True)  # للجسر الموثق فقط
    test_requested = serializers.BooleanField()
    roster_read_job_id = serializers.IntegerField(allow_null=True, required=False)
    roster_commands = serializers.ListField(required=False, default=list)
