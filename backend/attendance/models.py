"""حضور الحصص — Exception-Only Storage.

قواعد صلبة:
- الجلسة تخص (مدرسة، فصل، تاريخ، حصة) — قيد UNIQUE على period_sequence من الـ
  snapshot (لا على FK الحصة) ليصمد حتى لو استبدلت المدرسة حصص جدولها لاحقًا.
- bell_period_snapshot هو المرجع التاريخي الوحيد (ADR-010): تعديل الجدول لاحقًا
  لا يغير جلسات قديمة ولا حسابات تأخرها. FK الحصة SET_NULL للمرجعية الحية فقط.
- الهوية: submitted_by_membership (لا user وحده) — المستخدم متعدد المدارس.
- لا Mark للحاضر: بعد اعتماد الجلسة، الطالب بلا Mark = حاضر في هذه الجلسة فقط.
  غياب الجلسة نفسها لا يعني حضور أحد.
- student بـ PROTECT: أي حذف نهائي غير مسجل في PURGE_STEPS يفشل صاخبًا.
"""

from django.db import models

from common.models import TimestampedModel


class AttendanceSessionStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "قيد التحضير"
    SUBMITTED = "SUBMITTED", "معتمد"


class AttendanceSession(TimestampedModel):
    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="attendance_sessions"
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.PROTECT, related_name="attendance_sessions"
    )
    semester = models.ForeignKey(
        "academics.Semester",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="attendance_sessions",
    )
    section = models.ForeignKey(
        "students.Section", on_delete=models.PROTECT, related_name="attendance_sessions"
    )
    attendance_date = models.DateField()

    bell_period = models.ForeignKey(  # مرجع حي فقط — قد يصبح NULL عند استبدال الجدول
        "academics.BellPeriod",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_sessions",
    )
    period_sequence = models.PositiveSmallIntegerField()  # من الـ snapshot — ثابت
    bell_period_snapshot = models.JSONField()  # sequence/name/start/end/schedule/tz/date

    status = models.CharField(
        max_length=20,
        choices=AttendanceSessionStatus.choices,
        default=AttendanceSessionStatus.IN_PROGRESS,
    )
    roster_fingerprint = models.CharField(max_length=64)  # لكشف تغير الفصل قبل الاعتماد
    # snapshot مهلة التنبيه وقت الفتح (م7) — تغيير الإعداد لاحقًا لا يعيد كتابة
    # تاريخ الالتزام (جلسة اعتمدت «في الوقت» تبقى كذلك للأبد)
    unprepared_alert_minutes_snapshot = models.PositiveSmallIntegerField()

    started_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        on_delete=models.PROTECT,
        related_name="started_attendance_sessions",
    )
    submitted_by_membership = models.ForeignKey(
        "memberships.SchoolMembership",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="submitted_attendance_sessions",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "جلسة تحضير"
        verbose_name_plural = "جلسات التحضير"
        constraints = [
            # الحكم النهائي ضد التحضير المزدوج — حتى تحت التزامن
            models.UniqueConstraint(
                fields=["school", "section", "attendance_date", "period_sequence"],
                name="uniq_session_per_section_date_period",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "attendance_date", "period_sequence", "status"],
                name="att_school_date_period_idx",
            ),
            models.Index(
                fields=["school", "section", "attendance_date"],
                name="att_school_section_date_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.section} — {self.attendance_date} حصة {self.period_sequence}"
            f" ({self.status})"
        )


class AttendanceMarkStatus(models.TextChoices):
    ABSENT = "ABSENT", "غائب"
    LATE = "LATE", "متأخر"
    # EXCUSED يأتي في المرحلة 10 — التصميم يتسع له (حقل excuse_status لاحقًا)


class AttendanceMark(TimestampedModel):
    """استثناء فقط (غائب/متأخر) — الحاضر لا سجل له."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="attendance_marks"
    )
    session = models.ForeignKey(
        AttendanceSession, on_delete=models.CASCADE, related_name="marks"
    )
    student = models.ForeignKey(  # PROTECT: يفشل الحذف غير المسجل في Purge صاخبًا
        "students.Student", on_delete=models.PROTECT, related_name="attendance_marks"
    )
    status = models.CharField(max_length=10, choices=AttendanceMarkStatus.choices)
    arrival_time = models.TimeField(null=True, blank=True)  # للمتأخر
    late_minutes = models.PositiveSmallIntegerField(null=True, blank=True)  # يحسب خادميًا

    class Meta:
        verbose_name = "علامة حضور"
        verbose_name_plural = "علامات الحضور"
        constraints = [
            models.UniqueConstraint(
                fields=["session", "student"], name="uniq_mark_per_session_student"
            ),
        ]
        indexes = [
            models.Index(fields=["school", "student"], name="mark_school_student_idx"),
            models.Index(fields=["school", "status"], name="mark_school_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.student_id} — {self.status}"


class AttendanceChange(models.Model):
    """سجل تعديلات علائقي — التاريخ لا يمسح بصمت (يشمل PRESENT في المسارين)."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="attendance_changes"
    )
    session = models.ForeignKey(
        AttendanceSession, on_delete=models.CASCADE, related_name="changes"
    )
    student = models.ForeignKey(
        "students.Student", on_delete=models.PROTECT, related_name="attendance_changes"
    )
    actor_membership = models.ForeignKey(
        "memberships.SchoolMembership", on_delete=models.PROTECT, related_name="+"
    )
    previous_status = models.CharField(max_length=10)  # PRESENT/ABSENT/LATE
    new_status = models.CharField(max_length=10)
    previous_late_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    new_late_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    reason = models.CharField(max_length=300, blank=True, default="")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تعديل حضور"
        verbose_name_plural = "تعديلات الحضور"
        indexes = [
            models.Index(fields=["school", "session"], name="attchange_school_session_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.student_id}: {self.previous_status}→{self.new_status}"
