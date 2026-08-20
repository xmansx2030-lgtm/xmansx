"""سجل قوالب المستندات (البنود 21-25).

لا HTML داخل الـviews: كل مستند مفتاح في هذا السجل ← قالب Django ← إصدار مثبت.
المستند القديم يحتفظ بـ(‏template_key, template_version) فيبقى مفهومًا بعد تطور
القوالب: إضافة تصميم جديد تكون `v2` بمدخل جديد، لا تعديلًا لـ`v1`.

**سياسة النماذج الرسمية (البندان 24-25):** أي قالب هنا مصدره داخلي
(`source_type = INTERNAL`) ولا يوصف بأنه «نموذج وزاري معتمد». اعتماد نموذج رسمي
لاحقًا يتطلب مدخلًا جديدًا يحمل مرجع المصدر وإصداره وتاريخ سريانه — لا إعادة تسمية
لقالب داخلي.
"""

from dataclasses import dataclass

from documents.models import DocumentType


class TemplateSourceType:
    INTERNAL = "INTERNAL"  # صياغة داخلية للمنصة
    OFFICIAL = "OFFICIAL"  # نموذج رسمي موثق المصدر (غير مستخدم بعد)


@dataclass(frozen=True)
class DocumentTemplate:
    key: str
    version: str
    document_type: str
    title: str
    template_name: str
    source_type: str = TemplateSourceType.INTERNAL
    source_reference: str = ""
    source_version: str = ""
    effective_date: str = ""

    @property
    def registry_id(self) -> str:
        return f"{self.key}:{self.version}"


_TEMPLATES: tuple[DocumentTemplate, ...] = (
    DocumentTemplate(
        key="warning_level_1",
        version="v1",
        document_type=DocumentType.WARNING_LEVEL_1,
        title="إشعار إنذار أول",
        template_name="documents/warning.html",
    ),
    DocumentTemplate(
        key="warning_level_2",
        version="v1",
        document_type=DocumentType.WARNING_LEVEL_2,
        title="إشعار إنذار ثانٍ",
        template_name="documents/warning.html",
    ),
    DocumentTemplate(
        key="warning_level_3",
        version="v1",
        document_type=DocumentType.WARNING_LEVEL_3,
        title="إشعار إنذار ثالث",
        template_name="documents/warning.html",
    ),
    DocumentTemplate(
        key="attendance_commitment",
        version="v1",
        document_type=DocumentType.ATTENDANCE_COMMITMENT,
        title="تعهد الالتزام بالحضور والمواظبة",
        template_name="documents/commitment.html",
    ),
    DocumentTemplate(
        key="absence_detail_report",
        version="v1",
        document_type=DocumentType.ABSENCE_DETAIL_REPORT,
        title="كشف تفصيلي للغياب",
        template_name="documents/absence_report.html",
    ),
    DocumentTemplate(
        key="morning_late_report",
        version="v1",
        document_type=DocumentType.MORNING_LATE_DETAIL_REPORT,
        title="كشف تفصيلي للتأخر عن الدوام الصباحي",
        template_name="documents/morning_late_report.html",
    ),
    DocumentTemplate(
        key="period_late_report",
        version="v1",
        document_type=DocumentType.PERIOD_LATE_DETAIL_REPORT,
        title="كشف تفصيلي لتأخر الحصص",
        template_name="documents/period_late_report.html",
    ),
    DocumentTemplate(
        key="student_attendance_report",
        version="v1",
        document_type=DocumentType.STUDENT_ATTENDANCE_REPORT,
        title="تقرير مواظبة الطالب",
        template_name="documents/attendance_report.html",
    ),
)

BY_DOCUMENT_TYPE = {t.document_type: t for t in _TEMPLATES}
BY_REGISTRY_ID = {t.registry_id: t for t in _TEMPLATES}


def template_for(document_type: str) -> DocumentTemplate:
    """أحدث قالب لنوع مستند — يستخدم عند **الإنشاء** فقط."""
    from common.errors import ApiError

    template = BY_DOCUMENT_TYPE.get(document_type)
    if template is None:
        raise ApiError(
            "DOCUMENT_TEMPLATE_NOT_FOUND", "لا يوجد قالب لهذا النوع من المستندات.", status_code=404
        )
    return template


def template_of(document) -> DocumentTemplate:
    """قالب مستند موجود — بإصداره المثبت وقت الإصدار لا بأحدث إصدار."""
    from common.errors import ApiError

    template = BY_REGISTRY_ID.get(f"{document.template_key}:{document.template_version}")
    if template is None:
        raise ApiError(
            "DOCUMENT_TEMPLATE_VERSION_UNAVAILABLE",
            "إصدار قالب هذا المستند لم يعد متوفراً في النظام.",
            status_code=409,
        )
    return template
