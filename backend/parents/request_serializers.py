"""Explicit public API response contracts; no unrestricted model serializers."""

from drf_spectacular.utils import PolymorphicProxySerializer
from rest_framework import serializers

from excuses.models import ExcuseReasonType
from student_warnings.models import WarningLevel, WarningRuleType


class PaginationQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, max_value=1000, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False)


class PublicationQuerySerializer(PaginationQuerySerializer):
    case_id = serializers.IntegerField(min_value=1, required=False)


class NotificationQuerySerializer(PaginationQuerySerializer):
    relation_id = serializers.IntegerField(min_value=1, required=False)


class AttachmentOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    filename = serializers.CharField()
    mime_type = serializers.CharField()
    size_bytes = serializers.IntegerField()


class TargetOutputSerializer(serializers.Serializer):
    attendance_date = serializers.DateField()
    period_sequence = serializers.IntegerField(allow_null=True)


class ExcuseOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.ChoiceField(choices=["EXCUSE"])
    relation_id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    status = serializers.ChoiceField(
        choices=["PENDING", "NEEDS_INFO", "APPROVED", "REJECTED", "CANCELLED"]
    )
    reason_type = serializers.ChoiceField(choices=ExcuseReasonType.choices)
    notes = serializers.CharField(allow_blank=True)
    targets = TargetOutputSerializer(many=True)
    decision_note = serializers.CharField(allow_blank=True)
    administrative_excuse_id = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    attachments = AttachmentOutputSerializer(many=True)


class CorrectionOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.ChoiceField(choices=["CORRECTION"])
    relation_id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    session_id = serializers.IntegerField()
    attendance_date = serializers.DateField()
    period_sequence = serializers.IntegerField()
    session_updated_at = serializers.DateTimeField()
    status = serializers.ChoiceField(
        choices=["PENDING", "NEEDS_INFO", "APPROVED", "REJECTED", "CANCELLED"]
    )
    reason = serializers.CharField()
    decision_note = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class StaffExcuseOutputSerializer(ExcuseOutputSerializer):
    student_name = serializers.CharField()
    requester_name = serializers.CharField(allow_blank=True)


class StaffCorrectionOutputSerializer(CorrectionOutputSerializer):
    student_name = serializers.CharField()
    requester_name = serializers.CharField(allow_blank=True)


class DocumentOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.CharField()


class PublicationOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    title = serializers.CharField()
    body = serializers.CharField(allow_blank=True)
    required_action = serializers.CharField(allow_blank=True)
    due_at = serializers.DateTimeField(allow_null=True)
    published_at = serializers.DateTimeField()
    revoked_at = serializers.DateTimeField(allow_null=True)
    acknowledged_at = serializers.DateTimeField(allow_null=True)
    document = DocumentOutputSerializer(allow_null=True)


class PublicationAcknowledgementOutputSerializer(serializers.Serializer):
    relation_id = serializers.IntegerField()
    parent_name = serializers.CharField()
    acknowledged_at = serializers.DateTimeField()


class StaffPublicationOutputSerializer(PublicationOutputSerializer):
    ack_count = serializers.IntegerField()
    acknowledgements = PublicationAcknowledgementOutputSerializer(many=True)


class StaffAcknowledgementOutputSerializer(PublicationAcknowledgementOutputSerializer):
    id = serializers.IntegerField()
    type = serializers.ChoiceField(choices=["WARNING", "PUBLICATION"])
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    target_id = serializers.IntegerField()


class WarningDocumentOutputSerializer(serializers.Serializer):
    publication_id = serializers.IntegerField()
    document_type = serializers.CharField()
    status = serializers.CharField()


class WarningOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    warning_type = serializers.ChoiceField(choices=WarningRuleType.choices)
    level = serializers.ChoiceField(choices=WarningLevel.choices)
    status = serializers.ChoiceField(choices=["ISSUED", "VOIDED"])
    issued_at = serializers.DateTimeField()
    acknowledged_at = serializers.DateTimeField(allow_null=True)
    required_action = serializers.CharField(allow_blank=True)
    documents = WarningDocumentOutputSerializer(many=True)


class NotificationOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    relation_id = serializers.IntegerField()
    student_name = serializers.CharField(allow_null=True)
    school_name = serializers.CharField(allow_null=True)
    kind = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField(allow_blank=True)
    state = serializers.ChoiceField(choices=["NEW", "READ", "NEEDS_ACTION", "ACTION_COMPLETED"])
    requires_action = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    read_at = serializers.DateTimeField(allow_null=True)
    action_completed_at = serializers.DateTimeField(allow_null=True)


class AcknowledgementOutputSerializer(serializers.Serializer):
    acknowledged_at = serializers.DateTimeField()


class WarningAcknowledgementOutputSerializer(AcknowledgementOutputSerializer):
    meaning = serializers.CharField()


class PageOutputSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)


class ExcusePageOutputSerializer(PageOutputSerializer):
    items = ExcuseOutputSerializer(many=True)


class CorrectionPageOutputSerializer(PageOutputSerializer):
    items = CorrectionOutputSerializer(many=True)


class WarningPageOutputSerializer(PageOutputSerializer):
    items = WarningOutputSerializer(many=True)


class PublicationPageOutputSerializer(PageOutputSerializer):
    items = PublicationOutputSerializer(many=True)


class StaffPublicationPageOutputSerializer(PageOutputSerializer):
    items = StaffPublicationOutputSerializer(many=True)


class StaffAcknowledgementPageOutputSerializer(PageOutputSerializer):
    items = StaffAcknowledgementOutputSerializer(many=True)


class NotificationPageOutputSerializer(PageOutputSerializer):
    items = NotificationOutputSerializer(many=True)


class ParentRequestsPageOutputSerializer(PageOutputSerializer):
    items = PolymorphicProxySerializer(
        component_name="ParentRequestItem",
        serializers={"EXCUSE": ExcuseOutputSerializer, "CORRECTION": CorrectionOutputSerializer},
        resource_type_field_name="type",
        many=True,
    )


class StaffRequestsPageOutputSerializer(PageOutputSerializer):
    excuses = StaffExcuseOutputSerializer(many=True)
    corrections = StaffCorrectionOutputSerializer(many=True)
    items = PolymorphicProxySerializer(
        component_name="StaffParentRequestItem",
        serializers={
            "EXCUSE": StaffExcuseOutputSerializer,
            "CORRECTION": StaffCorrectionOutputSerializer,
        },
        resource_type_field_name="type",
        many=True,
    )
