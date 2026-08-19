"""QR الفصل — token عتيم يحدد الفصل فقط، لا يمنح أي صلاحية.

الوصول يتطلب دائمًا: مصادقة + عضوية فعالة + دور TEACHER + المدرسة النشطة نفسها.
طالب صوّر الرمز لا يستطيع شيئًا. التدوير يستبدل الـ token فيبطل القديم فورًا.
انحراف موثق: رمز واحد SECTION_QR_INVALID للرمز غير الصالح والمجدد معًا —
لا نخزن تاريخ tokens قديمة فلا يمكن (ولا يلزم أمنيًا) التمييز بينهما.
"""

import secrets

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from students.models import Section


def ensure_qr_token(*, section: Section, actor, request=None) -> str:
    if section.qr_token:
        return section.qr_token
    return rotate_qr_token(section=section, actor=actor, request=request)


def rotate_qr_token(*, section: Section, actor, request=None) -> str:
    section.qr_token = secrets.token_urlsafe(24)  # غير قابل للتخمين
    section.save(update_fields=["qr_token", "updated_at"])
    record_event(
        AuditAction.SECTION_QR_ROTATED,
        request=request,
        actor=actor,
        school=section.school,
        target_type="Section",
        target_id=section.id,
    )
    return section.qr_token


def resolve_qr_token(*, school, token: str) -> Section:
    """الحل داخل المدرسة النشطة حصرًا — رمز مدرسة أخرى غير موجود من منظور المستخدم
    (لا كشف لأي بيانات عن المدرسة الأخرى، ولا تبديل تلقائي للمدرسة)."""
    section = Section.objects.filter(
        school=school, qr_token=token, is_active=True
    ).select_related("grade").first()
    if section is None:
        raise ApiError(
            "SECTION_QR_INVALID",
            "رمز QR غير صالح أو تم تجديده — استخدم الاختيار اليدوي أو اطلب رمزًا محدثًا.",
            status_code=404,
        )
    return section
