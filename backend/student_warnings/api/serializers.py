"""‏Serializers الإنذارات — serializer-first (قاعدة OPENAPI.md).

قاعدة صلبة (البند 75): العميل لا يرسل أبدًا threshold_at_issue أو
metric_value_at_issue أو issued_by أو school أو أي snapshot — الخادم ينشئها.
"""

from rest_framework import serializers

from student_warnings.models import WarningLevel, WarningRuleType

# ---- الإدخال ----


class RuleLevelsSerializer(serializers.Serializer):
    LEVEL_1 = serializers.IntegerField(min_value=1, max_value=200)
    LEVEL_2 = serializers.IntegerField(min_value=1, max_value=200)
    LEVEL_3 = serializers.IntegerField(min_value=1, max_value=200)


class RuleTypeConfigSerializer(serializers.Serializer):
    is_enabled = serializers.BooleanField(required=False)
    levels = RuleLevelsSerializer()


class RulesPatchSerializer(serializers.Serializer):
    UNEXCUSED_FULL_DAY_ABSENCE = RuleTypeConfigSerializer(required=False)
    MORNING_LATE_OCCURRENCES = RuleTypeConfigSerializer(required=False)


class IssueWarningSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)
    warning_type = serializers.ChoiceField(choices=WarningRuleType.choices)
    level = serializers.ChoiceField(choices=WarningLevel.choices)
    notes = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class VoidWarningSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)


# ---- الإخراج ----


class RuleLevelsOutSerializer(serializers.Serializer):
    LEVEL_1 = serializers.IntegerField()
    LEVEL_2 = serializers.IntegerField()
    LEVEL_3 = serializers.IntegerField()


class RuleTypeOutSerializer(serializers.Serializer):
    is_enabled = serializers.BooleanField()
    levels = RuleLevelsOutSerializer()


class RulesResponseSerializer(serializers.Serializer):
    UNEXCUSED_FULL_DAY_ABSENCE = RuleTypeOutSerializer()
    MORNING_LATE_OCCURRENCES = RuleTypeOutSerializer()


class LevelStateSerializer(serializers.Serializer):
    threshold = serializers.IntegerField()
    state = serializers.ChoiceField(choices=["DUE", "NOT_DUE", "ISSUED"])


class EligibilityRowSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    full_name = serializers.CharField()
    grade_id = serializers.IntegerField()
    grade_name = serializers.CharField()
    section_name = serializers.CharField()
    warning_type = serializers.CharField()
    is_enabled = serializers.BooleanField()
    current_value = serializers.IntegerField()
    highest_reached_level = serializers.CharField(allow_null=True)
    highest_due_level = serializers.CharField(allow_null=True)
    issued_levels = serializers.ListField(child=serializers.CharField())
    levels = serializers.DictField(child=LevelStateSerializer())


class EligibilitySummarySerializer(serializers.Serializer):
    due_students = serializers.IntegerField()
    issued_students = serializers.IntegerField()


class EligibilityResponseSerializer(serializers.Serializer):
    academic_year = serializers.DictField()
    summary = serializers.DictField(child=EligibilitySummarySerializer())
    results = EligibilityRowSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class WarningSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    grade_name = serializers.CharField()
    section_name = serializers.CharField()
    warning_type = serializers.CharField()
    warning_type_label = serializers.CharField()
    level = serializers.CharField()
    level_label = serializers.CharField()
    status = serializers.CharField()
    threshold_at_issue = serializers.IntegerField()
    metric_value_at_issue = serializers.IntegerField()
    issued_at = serializers.DateTimeField()
    issued_by = serializers.CharField(allow_null=True)
    notes = serializers.CharField()
    voided_at = serializers.DateTimeField(allow_null=True)
    voided_by = serializers.CharField(allow_null=True)
    void_reason = serializers.CharField()


class WarningDetailSerializer(WarningSerializer):
    academic_year = serializers.CharField()
    current_metric_value = serializers.IntegerField()
    metric_drifted = serializers.BooleanField()
    snapshot = serializers.DictField()
