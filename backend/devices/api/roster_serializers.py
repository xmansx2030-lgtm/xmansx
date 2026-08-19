from rest_framework import serializers

from devices.models import DeviceRosterSyncAction, DeviceRosterSyncStatus


class NormalizedDeviceUserSerializer(serializers.Serializer):
    external_user_id = serializers.CharField(max_length=64)
    display_name = serializers.CharField(max_length=150, allow_blank=True)
    status = serializers.CharField(max_length=20, required=False, default="ACTIVE")
    metadata_minimal = serializers.DictField(required=False, default=dict)


class RosterAnalyzeSerializer(serializers.Serializer):
    device_id = serializers.IntegerField(min_value=1)


class BridgeRosterReadSerializer(serializers.Serializer):
    job_id = serializers.IntegerField(min_value=1)
    device_id = serializers.IntegerField(min_value=1)
    users = NormalizedDeviceUserSerializer(many=True)
    device_roster_version = serializers.CharField(max_length=64, required=False, allow_blank=True)


class BridgeRosterCommandSerializer(serializers.Serializer):
    job_id = serializers.IntegerField(min_value=1)
    item_id = serializers.IntegerField(min_value=1)
    command_id = serializers.CharField(max_length=64)
    result = serializers.ChoiceField(choices=["SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL"])
    error_code = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


class RosterSyncJobSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    device_id = serializers.IntegerField()
    device_name = serializers.CharField()
    status = serializers.ChoiceField(choices=DeviceRosterSyncStatus.choices)
    roster_version = serializers.CharField()
    device_roster_version = serializers.CharField()
    matched_count = serializers.IntegerField()
    create_count = serializers.IntegerField()
    update_count = serializers.IntegerField()
    delete_count = serializers.IntegerField()
    conflict_count = serializers.IntegerField()
    student_count = serializers.IntegerField()
    device_user_count = serializers.IntegerField()
    ready_at = serializers.DateTimeField(allow_null=True)
    approved_at = serializers.DateTimeField(allow_null=True)


class RosterSyncItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    student_id = serializers.IntegerField(allow_null=True)
    student_name = serializers.CharField(allow_null=True)
    external_user_id = serializers.CharField()
    action = serializers.ChoiceField(choices=DeviceRosterSyncAction.choices)
    status = serializers.CharField()
    reason = serializers.CharField()
    error_code = serializers.CharField()
    safe_before_snapshot = serializers.DictField()
    safe_after_snapshot = serializers.DictField()
