from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.mobile import normalize_mobile
from common.security.identifiers import normalize_student_identifier


class RegistrationSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=3, max_length=150)
    mobile = serializers.CharField(max_length=24)
    student_identifier = serializers.CharField(max_length=30, write_only=True)
    relationship_type = serializers.CharField(max_length=60, default="ولي أمر")

    def validate_mobile(self, value):
        try:
            return normalize_mobile(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError("رقم الجوال غير صالح.") from exc

    def validate_student_identifier(self, value):
        try:
            return normalize_student_identifier(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=40, max_length=128, write_only=True)


class ActivationSerializer(TokenSerializer):
    new_password = serializers.CharField(
        max_length=128, write_only=True, required=False, trim_whitespace=False
    )
    confirm_password = serializers.CharField(
        max_length=128, write_only=True, required=False, trim_whitespace=False
    )


class ReceiptSerializer(serializers.Serializer):
    receipt_token = serializers.CharField(min_length=40, max_length=128, write_only=True)
    applicant_note = serializers.CharField(max_length=600, required=False)


class RegistrationDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["APPROVE", "REJECT", "NEEDS_INFO"])
    student_id = serializers.IntegerField(min_value=1, required=False)
    verification_note = serializers.CharField(max_length=600, required=False, allow_blank=True)
    decision_reason = serializers.CharField(max_length=300, required=False, allow_blank=True)
    contact_bound = serializers.BooleanField(default=True)
    delivery = serializers.ChoiceField(choices=["SMS", "MANUAL"], default="SMS")


class RelationDecisionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ACTIVE", "SUSPENDED_CONTACT_REVIEW", "REVOKED"])
    reason = serializers.CharField(min_length=3, max_length=300)
    verification_note = serializers.CharField(max_length=600, required=False, allow_blank=True)
    contact_bound = serializers.BooleanField(required=False)


class SettingsSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()


class HistorySerializer(serializers.Serializer):
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)


class ResponseSerializer(serializers.Serializer):
    """Bounded endpoint projections documented in the implementation reference."""

    message = serializers.CharField(required=False)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)


class RegistrationMetadataSerializer(serializers.Serializer):
    school_name = serializers.CharField()
    school_id = serializers.IntegerField()
    enabled = serializers.BooleanField()


class RegistrationReceiptSerializer(ResponseSerializer):
    receipt_token = serializers.CharField()


class ReceiptStatusSerializer(ResponseSerializer):
    status = serializers.CharField()


class ActivationMetadataSerializer(serializers.Serializer):
    status = serializers.CharField()
    school_name = serializers.CharField()
    account_exists = serializers.BooleanField()
    requires_login = serializers.BooleanField()


class ParentAccountSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    mobile = serializers.CharField()
    name = serializers.CharField()
    has_parent_portal = serializers.BooleanField()
    must_change_password = serializers.BooleanField()
    memberships = serializers.ListField(child=serializers.DictField())
    invitations = serializers.ListField(child=serializers.DictField())
    active_school = serializers.DictField(allow_null=True)
    roles = serializers.ListField(child=serializers.CharField())
    capabilities = serializers.ListField(child=serializers.CharField())
    is_platform_admin = serializers.BooleanField()
    is_platform_owner = serializers.BooleanField()
    platform_role = serializers.CharField(allow_null=True)
    platform_role_label = serializers.CharField()
    platform_capabilities = serializers.ListField(child=serializers.CharField())


class FamilySchoolSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class ChildIdentitySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    full_name = serializers.CharField()
    grade_name = serializers.CharField()
    section_name = serializers.CharField()
    department = serializers.CharField()


class ParentDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    absence_status = serializers.CharField()
    absence_status_label = serializers.CharField()
    completeness_status = serializers.CharField()
    expected_periods = serializers.IntegerField()
    submitted_periods = serializers.IntegerField()
    present_periods = serializers.IntegerField()
    absent_periods = serializers.IntegerField()
    excused_absent_periods = serializers.IntegerField()
    unexcused_absent_periods = serializers.IntegerField()
    updated_at = serializers.DateTimeField(allow_null=True)


class MorningSerializer(serializers.Serializer):
    status = serializers.CharField()
    status_label = serializers.CharField()
    arrival_time = serializers.DateTimeField(allow_null=True)
    counted_late_minutes = serializers.IntegerField()
    updated_at = serializers.DateTimeField(allow_null=True)


class ChildSerializer(serializers.Serializer):
    relation_id = serializers.IntegerField()
    school = FamilySchoolSerializer()
    status = serializers.CharField()
    student = ChildIdentitySerializer(allow_null=True)
    today = ParentDaySerializer(required=False, allow_null=True)
    morning = MorningSerializer(required=False, allow_null=True)
    new_notifications = serializers.IntegerField(required=False)
    required_actions = serializers.IntegerField(required=False)


class ChildrenSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ChildSerializer(many=True)


class ParentPeriodSerializer(serializers.Serializer):
    sequence = serializers.IntegerField()
    period_sequence = serializers.IntegerField()
    name = serializers.CharField()
    start_time = serializers.CharField(allow_null=True)
    end_time = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    status_label = serializers.CharField()
    attendance_date = serializers.DateField()
    session_id = serializers.IntegerField(allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)
    excused = serializers.BooleanField()


class ChildDetailSerializer(serializers.Serializer):
    child = ChildSerializer()
    today = ParentDaySerializer()
    periods = ParentPeriodSerializer(many=True)
    morning = MorningSerializer()


class HistoryDaySerializer(ParentDaySerializer):
    morning = MorningSerializer()


class HistorySummarySerializer(serializers.Serializer):
    full_absence_days = serializers.IntegerField()
    partial_absence_days = serializers.IntegerField()
    incomplete_days = serializers.IntegerField()
    present_periods = serializers.IntegerField()
    absent_periods = serializers.IntegerField()
    excused_absent_periods = serializers.IntegerField()
    unexcused_absent_periods = serializers.IntegerField()
    morning_late_days = serializers.IntegerField()
    counted_late_minutes = serializers.IntegerField()


class ParentHistorySerializer(serializers.Serializer):
    results = HistoryDaySerializer(many=True)
    summary = HistorySummarySerializer()
    from_date = serializers.DateField()
    to_date = serializers.DateField()


class RegistrationRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    mobile_masked = serializers.CharField()
    relationship_type = serializers.CharField()
    status = serializers.CharField()
    student_id = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()
    reviewed_at = serializers.DateTimeField(allow_null=True)
    decision_reason = serializers.CharField()
    applicant_note = serializers.CharField()


class RegistrationPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = RegistrationRowSerializer(many=True)


class RegistrationReviewRowSerializer(RegistrationRowSerializer):
    mobile = serializers.CharField()


class StudentMatchSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    full_name = serializers.CharField()
    national_id_masked = serializers.CharField()
    guardian_name = serializers.CharField(required=False)
    guardian_mobile = serializers.CharField(required=False)
    contact_revision = serializers.IntegerField(required=False)


class ActivationRecordSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    delivery_status = serializers.CharField()
    failure_code = serializers.CharField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    used_at = serializers.DateTimeField(allow_null=True)
    revoked_at = serializers.DateTimeField(allow_null=True)


class RegistrationReviewSerializer(serializers.Serializer):
    request = RegistrationReviewRowSerializer()
    student_match = StudentMatchSerializer(allow_null=True)
    sibling_candidates = StudentMatchSerializer(many=True)
    existing_relations = serializers.ListField(child=serializers.DictField())
    activations = ActivationRecordSerializer(many=True)


class ActivationDeliverySerializer(serializers.Serializer):
    request = RegistrationRowSerializer(required=False)
    activation_url = serializers.URLField(required=False)
    delivery_status = serializers.CharField(required=False)


class StaffRelationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    parent_name = serializers.CharField()
    mobile_masked = serializers.CharField()
    status = serializers.CharField()
    relationship_type = serializers.CharField()
    contact_bound = serializers.BooleanField()
    contact_revision = serializers.IntegerField()
    approval_revision = serializers.IntegerField()
    suspension_reason = serializers.CharField()


class StaffRelationsSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = StaffRelationSerializer(many=True)


class RelationDecisionResultSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()


class ParentSettingsResultSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    registration_url = serializers.URLField(allow_null=True)
    stats = serializers.DictField(child=serializers.FloatField())
