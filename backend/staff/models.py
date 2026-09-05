"""دليل الموظفين واستيراد المعلمين.

قواعد صلبة:
- لا TeacherUser جديد: الهوية = User العالمي، والانتماء = SchoolMembership،
  والأدوار = SchoolMembershipRole. StaffProfile يحمل فقط بيانات الموظف
  الخاصة بالمدرسة (اسم عرض/رقم وظيفي) — لا role فيه ولا يعدل User العالمي.
- الاستيراد يمنح TEACHER فقط — الملف لا يمنح أدوارًا إدارية (منع تصعيد صلاحيات).
"""

from django.conf import settings
from django.db import models

from common.models import TimestampedModel


class StaffSource(models.TextChoices):
    IMPORT = "IMPORT", "استيراد"
    MANUAL = "MANUAL", "يدوي"


class StaffProfile(TimestampedModel):
    """بيانات الموظف الخاصة بالمدرسة — نفس User قد يملك Profile مختلفًا في كل مدرسة."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="staff_profiles"
    )
    membership = models.OneToOneField(
        "memberships.SchoolMembership", on_delete=models.CASCADE, related_name="staff_profile"
    )
    display_name = models.CharField("اسم العرض", max_length=200)
    # null مقصود (noqa DJ001): القيد الجزئي الفريد يشترط IS NOT NULL
    employee_number = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001
    job_title = models.CharField(max_length=100, blank=True, default="")
    source = models.CharField(
        max_length=10, choices=StaffSource.choices, default=StaffSource.MANUAL
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "ملف موظف"
        verbose_name_plural = "ملفات الموظفين"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "employee_number"],
                condition=models.Q(employee_number__isnull=False),
                name="uniq_employee_number_per_school",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "display_name"], name="staff_school_name_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} — {self.school}"


class CounselorSectionAssignment(TimestampedModel):
    """المرشد الأساسي للفصل — فصل واحد لا يملك أكثر من مرشد مسؤول.

    الإسناد تشغيلي للحالات الجديدة فقط؛ تغيير المرشد هنا لا يعيد كتابة
    الإحالات أو الحالات الإرشادية التاريخية التي سبق إسنادها.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="counselor_section_assignments",
    )
    section = models.OneToOneField(
        "students.Section",
        on_delete=models.CASCADE,
        related_name="counselor_assignment",
    )
    counselor_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        on_delete=models.CASCADE,
        related_name="counselor_section_assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "إسناد فصل لمرشد"
        verbose_name_plural = "إسنادات الفصول للمرشدين"
        indexes = [
            models.Index(
                fields=["school", "counselor_membership"],
                name="counselor_section_owner_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.section} → {self.counselor_membership}"


class StaffImportStatus(models.TextChoices):
    UPLOADED = "UPLOADED", "مرفوع"
    PROCESSING = "PROCESSING", "قيد المعالجة"
    READY_FOR_REVIEW = "READY_FOR_REVIEW", "جاهز للمراجعة"
    IMPORTING = "IMPORTING", "جارٍ الاستيراد"
    COMPLETED = "COMPLETED", "مكتمل"
    FAILED = "FAILED", "فشل"
    CANCELLED = "CANCELLED", "ملغى"


def staff_import_file_path(instance, filename: str) -> str:
    return f"staff_imports/school_{instance.school_id}/job_{instance.pk or 'new'}.xlsx"


class StaffImportJob(TimestampedModel):
    """مهمة استيراد معلمين — نفس نمط استيراد الطلاب (tenant من الـ Job في Celery)."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="staff_import_jobs"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="staff_import_jobs"
    )
    original_filename = models.CharField(max_length=255)
    file = models.FileField(upload_to=staff_import_file_path, null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=StaffImportStatus.choices, default=StaffImportStatus.UPLOADED
    )
    column_mapping = models.JSONField(default=dict, blank=True)
    headers = models.JSONField(default=list, blank=True)

    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)
    new_user_rows = models.PositiveIntegerField(default=0)
    existing_user_rows = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)  # لا كلمات مرور هنا أبدًا
    error_code = models.CharField(max_length=50, blank=True, default="")

    validated_at = models.DateTimeField(null=True, blank=True)
    committed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "مهمة استيراد موظفين"
        verbose_name_plural = "مهام استيراد الموظفين"
        constraints = [
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(status__in=["PROCESSING", "IMPORTING"]),
                name="uniq_running_staff_import_per_school",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "status"], name="staff_import_status_idx"),
        ]

    def __str__(self) -> str:
        return f"StaffImport #{self.pk} — {self.school} ({self.status})"


class StaffRowStatus(models.TextChoices):
    NEW = "NEW", "معلم جديد"
    EXISTING_USER_INVITE = "EXISTING_USER_INVITE", "حساب موجود — دعوة"
    ADD_TEACHER_ROLE = "ADD_TEACHER_ROLE", "إضافة دور معلم"
    PROFILE_UPDATE = "PROFILE_UPDATE", "تحديث بيانات"
    EXISTING_UNCHANGED = "EXISTING_UNCHANGED", "بلا تغيير"
    INVITATION_PENDING = "INVITATION_PENDING", "دعوة قائمة"
    NEEDS_MANUAL_ACTION = "NEEDS_MANUAL_ACTION", "يتطلب إجراء يدويًا"
    ERROR = "ERROR", "خطأ"
    DUPLICATE_IN_FILE = "DUPLICATE_IN_FILE", "مكرر في الملف"


class StaffImportRow(models.Model):
    """Staging مؤقت — الجوال يخزن مطبعًا (لازم للاعتماد) + masked للعرض،
    ولا يظهر كاملًا في المعاينة/الملخص. يحذف بعد انتهاء المهمة."""

    job = models.ForeignKey(StaffImportJob, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    mobile = models.CharField(max_length=16, blank=True, default="")
    data = models.JSONField(default=dict)
    status = models.CharField(max_length=30, choices=StaffRowStatus.choices)
    error_codes = models.JSONField(default=list, blank=True)
    error_message = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["row_number"]
        indexes = [models.Index(fields=["job", "status"], name="staff_row_job_status_idx")]

    def __str__(self) -> str:
        return f"Row {self.row_number} ({self.status})"
