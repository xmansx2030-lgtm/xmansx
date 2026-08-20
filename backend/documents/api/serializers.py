"""مخططات الإدخال — العميل يرسل نية فقط: نوع المستند والطالب ومدى التواريخ.

**ممنوع** قبول أي قيمة لقطة من العميل (`metric_value_at_issue`, `threshold_at_issue`,
`snapshot_data`, `generated_by`, `school`) — البند 92. عدم تعريفها هنا يجعل DRF
يتجاهلها، والخادم يعيد بناء كل شيء.
"""

from rest_framework import serializers

from documents.models import DocumentType


class GenerateDocumentSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    document_type = serializers.ChoiceField(choices=DocumentType.values)
    warning_id = serializers.IntegerField(required=False, allow_null=True)
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    create_action = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)


class PreviewDocumentSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    document_type = serializers.ChoiceField(choices=DocumentType.values)
    warning_id = serializers.IntegerField(required=False, allow_null=True)
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)


class VoidDocumentSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)


class DocumentSerializer(serializers.Serializer):
    """للتوثيق فقط — الاستجابة تبنى في الـview."""

    id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    document_type = serializers.CharField()
    document_type_label = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    template = serializers.CharField()
    warning_id = serializers.IntegerField(allow_null=True)
    action_id = serializers.IntegerField(allow_null=True)
    generated_at = serializers.CharField(allow_null=True)
    generated_by_name = serializers.CharField(allow_null=True)
    size_bytes = serializers.IntegerField()
    checksum = serializers.CharField()
    error_code = serializers.CharField()
    can_download = serializers.BooleanField()
