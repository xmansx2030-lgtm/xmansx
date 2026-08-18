"""الطلاب والصفوف والفصول والقيد التاريخي واستيراد نور.

قواعد صلبة:
- Student = هوية الطالب داخل المدرسة؛ StudentEnrollment = وضعه الدراسي في فترة.
  لا grade/section مباشرة على Student.
- رقم الهوية: مشفر + HMAC hash — UNIQUE(school, hash) داخل المدرسة لا عالميًا،
  ولا يظهر plaintext في أي مكان (staging مشفر أيضًا).
- لا حذف طلاب بسبب غيابهم عن ملف جديد — Status/إنهاء قيد فقط (ADR-010).
"""

from django.conf import settings
from django.db import models

from common.models import TimestampedModel
from common.security.identifiers import mask_national_id


class Grade(TimestampedModel):
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="grades")
    name = models.CharField("اسم الصف", max_length=100)  # الأول الثانوي
    code = models.CharField("الرمز", max_length=50)  # normalized key للمطابقة
    sequence = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "صف"
        verbose_name_plural = "الصفوف"
        ordering = ["sequence", "code"]
        constraints = [
            models.UniqueConstraint(fields=["school", "code"], name="uniq_grade_code_per_school"),
        ]

    def __str__(self) -> str:
        return f"{self.name} — {self.school}"


class Section(TimestampedModel):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="sections"
    )
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name="sections")
    name = models.CharField("اسم الفصل", max_length=50)  # للعرض: 1 أو أ
    code = models.CharField("الرمز", max_length=50)  # normalized key
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "فصل"
        verbose_name_plural = "الفصول"
        ordering = ["grade__sequence", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "grade", "code"], name="uniq_section_code_per_grade"
            ),
        ]
        indexes = [models.Index(fields=["school", "grade"], name="section_school_grade_idx")]

    def __str__(self) -> str:
        return f"{self.grade.name} / {self.name}"


class StudentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "نشط"
    GRADUATED = "GRADUATED", "متخرج"
    TRANSFERRED = "TRANSFERRED", "منتقل"
    WITHDRAWN = "WITHDRAWN", "منسحب"
    INACTIVE = "INACTIVE", "غير نشط"
    ARCHIVED = "ARCHIVED", "مؤرشف"


class Student(TimestampedModel):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="students"
    )
    national_id_encrypted = models.TextField()  # Fernet — لا يقرأ إلا عبر الخدمة
    national_id_lookup_hash = models.CharField(max_length=64)  # HMAC-SHA256 للبحث الدقيق
    national_id_masked = models.CharField(max_length=12)  # ******1234 للعرض بلا فك تشفير
    # null مقصود (noqa DJ001): القيد الجزئي الفريد يشترط IS NOT NULL — النص الفارغ سيتصادم
    student_number = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001
    full_name = models.CharField("اسم الطالب", max_length=200)
    guardian_name = models.CharField(max_length=150, blank=True, default="")
    guardian_mobile = models.CharField(max_length=16, blank=True, default="")  # مطبع إن وجد
    status = models.CharField(
        max_length=20, choices=StudentStatus.choices, default=StudentStatus.ACTIVE
    )
    # دورة الحياة (المرحلة 4.1)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    exit_date = models.DateField(null=True, blank=True)
    exit_reason = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "طالب"
        verbose_name_plural = "الطلاب"
        constraints = [
            # داخل المدرسة فقط — نفس الشخص قد يظهر في مدارس مختلفة (سجلات مستقلة)
            models.UniqueConstraint(
                fields=["school", "national_id_lookup_hash"],
                name="uniq_student_nid_per_school",
            ),
            models.UniqueConstraint(
                fields=["school", "student_number"],
                condition=models.Q(student_number__isnull=False),
                name="uniq_student_number_per_school",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "status"], name="student_school_status_idx"),
            models.Index(fields=["school", "full_name"], name="student_school_name_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.national_id_masked})"

    @staticmethod
    def mask(normalized_id: str) -> str:
        return mask_national_id(normalized_id)


class EnrollmentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "منتظم"
    TRANSFERRED = "TRANSFERRED", "منقول"
    COMPLETED = "COMPLETED", "مكتمل"
    WITHDRAWN = "WITHDRAWN", "منسحب"
    ARCHIVED = "ARCHIVED", "مؤرشف"


class StudentEnrollment(TimestampedModel):
    """قيد الطالب في عام دراسي/صف/فصل — التاريخ لا يحذف: الانتقال = إنهاء + جديد."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="enrollments"
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.PROTECT, related_name="enrollments"
    )
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="enrollments")
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="enrollments")
    status = models.CharField(
        max_length=20, choices=EnrollmentStatus.choices, default=EnrollmentStatus.ACTIVE
    )
    enrolled_at = models.DateField()
    ended_at = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "قيد دراسي"
        verbose_name_plural = "القيود الدراسية"
        constraints = [
            # قيد فعال واحد للطالب في العام الواحد — الحكم النهائي ضد التزامن
            models.UniqueConstraint(
                fields=["student", "academic_year"],
                condition=models.Q(status="ACTIVE"),
                name="uniq_active_enrollment_per_year",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "academic_year", "status"], name="enroll_school_year_idx"
            ),
            models.Index(fields=["section", "status"], name="enroll_section_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.student} → {self.section} ({self.status})"


class ImportJobStatus(models.TextChoices):
    UPLOADED = "UPLOADED", "مرفوع"
    PROCESSING = "PROCESSING", "قيد المعالجة"
    READY_FOR_REVIEW = "READY_FOR_REVIEW", "جاهز للمراجعة"
    IMPORTING = "IMPORTING", "جارٍ الاستيراد"
    COMPLETED = "COMPLETED", "مكتمل"
    FAILED = "FAILED", "فشل"
    CANCELLED = "CANCELLED", "ملغى"


def import_file_path(instance, filename: str) -> str:
    # اسم مخزن مولد — الاسم الأصلي حقل بيانات فقط (تعقيم)
    return f"student_imports/school_{instance.school_id}/job_{instance.pk or 'new'}.xlsx"


class StudentImportJob(TimestampedModel):
    """مهمة استيراد نور — تحفظ المدرسة والعام وقت الإنشاء (Celery tenant safety).

    سياسة الملف المؤقت (PII): يحذف مع صفوف الـ staging عند COMPLETED/CANCELLED/FAILED.
    لا يوفر تنزيل للملف الأصلي.
    """

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="import_jobs"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="import_jobs"
    )
    academic_year = models.ForeignKey(  # snapshot وقت الإنشاء — يتحقق عند Commit
        "academics.AcademicYear", on_delete=models.PROTECT, related_name="import_jobs"
    )
    original_filename = models.CharField(max_length=255)
    file = models.FileField(upload_to=import_file_path, null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=ImportJobStatus.choices, default=ImportJobStatus.UPLOADED
    )
    column_mapping = models.JSONField(default=dict, blank=True)
    headers = models.JSONField(default=list, blank=True)

    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=50, blank=True, default="")

    validated_at = models.DateTimeField(null=True, blank=True)
    committed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "مهمة استيراد طلاب"
        verbose_name_plural = "مهام استيراد الطلاب"
        constraints = [
            # لا استيرادان جاريان لنفس المدرسة
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(status__in=["PROCESSING", "IMPORTING"]),
                name="uniq_running_import_per_school",
            ),
        ]
        indexes = [models.Index(fields=["school", "status"], name="import_school_status_idx")]

    def __str__(self) -> str:
        return f"Import #{self.pk} — {self.school} ({self.status})"


class PurgeJobStatus(models.TextChoices):
    PENDING = "PENDING", "بانتظار التنفيذ"
    RUNNING = "RUNNING", "قيد التنفيذ"
    COMPLETED = "COMPLETED", "مكتمل"
    PARTIALLY_FAILED = "PARTIALLY_FAILED", "مكتمل جزئيًا"
    FAILED = "FAILED", "فشل"


class StudentPurgeJob(TimestampedModel):
    """حذف نهائي جماعي عبر Celery.

    الخصوصية (البند 29-30): student_ids تعيش أثناء التنفيذ فقط وتمسح عند
    الاكتمال — لا يبقى في الـ Job أو الـ Audit أي معرف قابل للربط بطالب محذوف؛
    فقط أعداد وسبب.
    """

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="purge_jobs"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="purge_jobs"
    )
    reason = models.CharField(max_length=100, blank=True, default="")  # مثل: GRADUATED
    status = models.CharField(
        max_length=20, choices=PurgeJobStatus.choices, default=PurgeJobStatus.PENDING
    )
    student_ids = models.JSONField(default=list, blank=True)  # تمسح بعد الاكتمال

    total_students = models.PositiveIntegerField(default=0)
    processed_students = models.PositiveIntegerField(default=0)
    deleted_students = models.PositiveIntegerField(default=0)
    failed_students = models.PositiveIntegerField(default=0)
    db_records_deleted = models.PositiveIntegerField(default=0)
    storage_objects_deleted = models.PositiveIntegerField(default=0)
    storage_objects_failed = models.PositiveIntegerField(default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "مهمة حذف نهائي"
        verbose_name_plural = "مهام الحذف النهائي"
        constraints = [
            # لا عمليتا حذف جاريتان لنفس المدرسة
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(status__in=["PENDING", "RUNNING"]),
                name="uniq_running_purge_per_school",
            ),
        ]

    def __str__(self) -> str:
        return f"Purge #{self.pk} — {self.school} ({self.status})"


class ImportRowStatus(models.TextChoices):
    NEW = "NEW", "جديد"
    EXISTING_UNCHANGED = "EXISTING_UNCHANGED", "بلا تغيير"
    EXISTING_UPDATED = "EXISTING_UPDATED", "تحديث بيانات"
    SECTION_CHANGED = "SECTION_CHANGED", "انتقال فصل"
    GRADE_CHANGED = "GRADE_CHANGED", "تغير صف"
    ERROR = "ERROR", "خطأ"
    DUPLICATE_IN_FILE = "DUPLICATE_IN_FILE", "مكرر في الملف"


class StudentImportRow(models.Model):
    """Staging مؤقت لصف من الملف — يحذف بعد انتهاء المهمة (ليس تاريخًا دائمًا).

    رقم الهوية لا يخزن plaintext: مشفر + hash + masked فقط.
    """

    job = models.ForeignKey(StudentImportJob, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    national_id_encrypted = models.TextField(blank=True, default="")
    national_id_hash = models.CharField(max_length=64, blank=True, default="")
    data = models.JSONField(default=dict)  # full_name, grade/section labels+codes, masked id...
    status = models.CharField(max_length=30, choices=ImportRowStatus.choices)
    error_codes = models.JSONField(default=list, blank=True)
    error_message = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "صف استيراد"
        verbose_name_plural = "صفوف الاستيراد"
        ordering = ["row_number"]
        indexes = [models.Index(fields=["job", "status"], name="import_row_job_status_idx")]

    def __str__(self) -> str:
        return f"Row {self.row_number} ({self.status})"
