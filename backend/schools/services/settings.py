"""خدمات إعدادات المدرسة — school وactor صريحان دائمًا (نمط MULTI_TENANCY.md)."""

from datetime import time

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from common.validators import validate_logo_image
from schools.models import School, SchoolSettings

# الحقول القابلة للتعديل عبر الخدمة — school/logo لهما مسارات خاصة (منع mass assignment)
SETTINGS_EDITABLE_FIELDS = {
    "ministry_school_number",
    "education_stage",
    "city",
    "official_principal_name",
    "timezone",
    "attendance_edit_window_minutes",
    "unprepared_period_alert_minutes",
    "school_day_start_time",
    "morning_late_grace_minutes",
}


def _audit_value(value):
    """حوّل الأنواع غير المدعومة في JSON إلى قيمة مقروءة في سجل التدقيق."""
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return value


def get_or_create_settings(*, school: School) -> SchoolSettings:
    settings_obj, _ = SchoolSettings.objects.get_or_create(school=school)
    return settings_obj


@transaction.atomic
def update_school_info(*, school: School, actor, data: dict, request=None) -> SchoolSettings:
    """تحديث اسم المدرسة و/أو حقول الإعدادات مع Audit بالحقول المتغيرة فقط."""
    settings_obj = get_or_create_settings(school=school)
    changed: dict[str, dict] = {}

    new_name = data.get("name")
    if new_name is not None and new_name != school.name:
        if not new_name.strip():
            raise ApiError("VALIDATION_ERROR", "اسم المدرسة لا يمكن أن يكون فارغاً.")
        changed["name"] = {"from": school.name, "to": new_name}
        school.name = new_name.strip()
        school.save(update_fields=["name", "updated_at"])
        record_event(
            AuditAction.SCHOOL_NAME_UPDATED,
            request=request,
            actor=actor,
            school=school,
            metadata={"changed": {"name": changed["name"]}},
        )

    new_school_type = data.get("school_type")
    if new_school_type is not None and new_school_type != school.school_type:
        school_type_change = {"from": school.school_type, "to": new_school_type}
        school.school_type = new_school_type
        school.save(update_fields=["school_type", "updated_at"])
        record_event(
            AuditAction.SCHOOL_SETTINGS_UPDATED,
            request=request,
            actor=actor,
            school=school,
            metadata={"changed": {"school_type": school_type_change}},
        )

    settings_changed: dict[str, dict] = {}
    for field in SETTINGS_EDITABLE_FIELDS:
        if field in data:
            old = getattr(settings_obj, field)
            new = data[field]
            if old != new:
                settings_changed[field] = {
                    "from": _audit_value(old),
                    "to": _audit_value(new),
                }
                setattr(settings_obj, field, new)

    if settings_changed:
        try:
            settings_obj.full_clean()
        except DjangoValidationError as exc:
            if (
                "unprepared_period_alert_minutes" in exc.message_dict
                or "attendance_edit_window_minutes" in exc.message_dict
            ):
                raise ApiError(
                    "INVALID_ALERT_MINUTES",
                    "قيمة الدقائق يجب أن تكون ضمن النطاق المسموح (0–120، والتنبيه 1–120).",
                ) from exc
            raise ApiError(
                "VALIDATION_ERROR", "البيانات المدخلة غير صحيحة.", details=exc.message_dict
            ) from exc
        settings_obj.save()
        record_event(
            AuditAction.SCHOOL_SETTINGS_UPDATED,
            request=request,
            actor=actor,
            school=school,
            metadata={"changed": settings_changed},
        )

    return settings_obj


def set_logo(*, school: School, actor, uploaded_file, request=None) -> SchoolSettings:
    """تحقق رباعي (حجم/امتداد/MIME عبر Pillow/سلامة) ثم حفظ — لا يخزن الملف في metadata."""
    try:
        validate_logo_image(uploaded_file)
    except DjangoValidationError as exc:
        raise ApiError("VALIDATION_ERROR", exc.messages[0]) from exc

    settings_obj = get_or_create_settings(school=school)
    if settings_obj.logo:
        settings_obj.logo.delete(save=False)
    settings_obj.logo = uploaded_file
    settings_obj.save(update_fields=["logo", "updated_at"])
    record_event(
        AuditAction.SCHOOL_SETTINGS_UPDATED,
        request=request,
        actor=actor,
        school=school,
        metadata={"changed": {"logo": {"to": "uploaded"}}},
    )
    return settings_obj


def remove_logo(*, school: School, actor, request=None) -> SchoolSettings:
    settings_obj = get_or_create_settings(school=school)
    if settings_obj.logo:
        settings_obj.logo.delete(save=False)
        settings_obj.logo = None
        settings_obj.save(update_fields=["logo", "updated_at"])
        record_event(
            AuditAction.SCHOOL_SETTINGS_UPDATED,
            request=request,
            actor=actor,
            school=school,
            metadata={"changed": {"logo": {"to": "removed"}}},
        )
    return settings_obj
