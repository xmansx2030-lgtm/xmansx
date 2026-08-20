"""المستندات المولدة (م12) — نسخة مجمدة كما صدرت، لا إعادة توليد من البيانات الحالية.

القاعدة الحاكمة (البنود 16-17): عند الإصدار يجمد `snapshot_data` ويولد ملف PDF
ويخزن؛ وإعادة الطباعة **تعيد الملف المخزن نفسه**. تغير مقاييس الطالب أو قواعد
الإنذارات أو صفه لاحقًا لا يغير مستندًا صدر.

- ‏`storage_key` = `file.name` (مسار عشوائي داخل مخزن خاص بلا رابط عام).
- ‏`snapshot_schema_version` يسمح بقراءة مستندات قديمة بعد تطور بنية اللقطة،
  و`template_version` يثبت القالب الذي رسمها.
- ‏student بـ PROTECT: نسيان تسجيل الحذف النهائي يفشل صاخبًا (إلزام م4.1).
"""

from django.db import models

from common.models import TimestampedModel
from documents.storage import PrivateDocumentStorage, generated_document_path

SNAPSHOT_SCHEMA_VERSION = 1


class DocumentType(models.TextChoices):
    WARNING_LEVEL_1 = "WARNING_LEVEL_1", "الإنذار الأول"
    WARNING_LEVEL_2 = "WARNING_LEVEL_2", "الإنذار الثاني"
    WARNING_LEVEL_3 = "WARNING_LEVEL_3", "الإنذار الثالث"
    ATTENDANCE_COMMITMENT = "ATTENDANCE_COMMITMENT", "تعهد الالتزام بالحضور"
    ABSENCE_DETAIL_REPORT = "ABSENCE_DETAIL_REPORT", "كشف تفصيلي للغياب"
    MORNING_LATE_DETAIL_REPORT = "MORNING_LATE_DETAIL_REPORT", "كشف تفصيلي للتأخر الصباحي"
    PERIOD_LATE_DETAIL_REPORT = "PERIOD_LATE_DETAIL_REPORT", "كشف تفصيلي لتأخر الحصص"
    STUDENT_ATTENDANCE_REPORT = "STUDENT_ATTENDANCE_REPORT", "تقرير مواظبة الطالب"


WARNING_DOCUMENT_TYPES = {
    "LEVEL_1": DocumentType.WARNING_LEVEL_1,
    "LEVEL_2": DocumentType.WARNING_LEVEL_2,
    "LEVEL_3": DocumentType.WARNING_LEVEL_3,
}

# المستندات التي تحتاج مدى تواريخ من المستخدم (بقيتها تعتمد لقطة الإنذار/العام)
RANGE_DOCUMENT_TYPES = {
    DocumentType.ABSENCE_DETAIL_REPORT,
    DocumentType.MORNING_LATE_DETAIL_REPORT,
    DocumentType.PERIOD_LATE_DETAIL_REPORT,
    DocumentType.STUDENT_ATTENDANCE_REPORT,
}


class DocumentStatus(models.TextChoices):
    PENDING = "PENDING", "قيد الإنشاء"
    READY = "READY", "جاهز"
    FAILED = "FAILED", "فشل الإنشاء"
    VOIDED = "VOIDED", "ملغى"


class GeneratedDocument(TimestampedModel):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="generated_documents"
    )
    student = models.ForeignKey(  # PROTECT: حارس تسجيل Purge
        "students.Student", on_delete=models.PROTECT, related_name="documents"
    )
    warning = models.ForeignKey(
        "student_warnings.StudentWarning",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    action = models.ForeignKey(
        "student_actions.StudentAction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents",
    )

    document_type = models.CharField(max_length=32, choices=DocumentType.choices)
    template_key = models.CharField(max_length=64)
    template_version = models.CharField(max_length=10)
    snapshot_schema_version = models.PositiveSmallIntegerField(default=SNAPSHOT_SCHEMA_VERSION)

    status = models.CharField(
        max_length=10, choices=DocumentStatus.choices, default=DocumentStatus.PENDING
    )
    # كل ما يلزم لإعادة فهم/إعادة رسم المستند كما صدر — بلا رقم هوية صريح (البند 19)
    snapshot_data = models.JSONField(default=dict)

    file = models.FileField(
        upload_to=generated_document_path,
        storage=PrivateDocumentStorage,
        blank=True,
        null=True,
    )
    mime_type = models.CharField(max_length=50, blank=True, default="")
    size_bytes = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True, default="")  # SHA-256 hex

    # نسخة أصلية واحدة لكل (إنذار، نوع)؛ إعادة الإصدار تكون بزيادة صريحة (البند 76)
    revision = models.PositiveSmallIntegerField(default=1)
    error_code = models.CharField(max_length=64, blank=True, default="")

    generated_by_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
    generated_at = models.DateTimeField(null=True, blank=True)

    voided_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "مستند مولد"
        verbose_name_plural = "المستندات المولدة"
        constraints = [
            # الحكم النهائي ضد النقر المزدوج (البند 77): نسخة حية واحدة لكل
            # (إنذار، نوع، مراجعة). الملغى/الفاشل لا يحجز المكان.
            models.UniqueConstraint(
                fields=["warning", "document_type", "revision"],
                condition=models.Q(
                    status__in=[DocumentStatus.PENDING, DocumentStatus.READY]
                ),
                name="uniq_live_warning_document",
            ),
            # ‏READY لا تكون بلا ملف: يمنع ادعاء الجاهزية (البند 120)
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=DocumentStatus.READY)
                    | (models.Q(file__isnull=False) & ~models.Q(file=""))
                ),
                name="document_ready_requires_file",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "student", "-generated_at"], name="doc_school_student_idx"
            ),
            models.Index(fields=["school", "document_type"], name="doc_school_type_idx"),
            models.Index(fields=["warning"], name="doc_warning_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.document_type} — طالب {self.student_id} ({self.status})"

    @property
    def storage_key(self) -> str:
        return self.file.name or ""
