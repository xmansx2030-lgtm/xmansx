"""نشر تغييرات جدول الحصص إلى القراءات التشغيلية الحالية."""

from django.db import transaction


def publish_live_schedule_change(*, school_id: int) -> None:
    """حدّث لقطة اليوم غير المستخدمة وأبطل كاش لوحة المدرسة بعد نجاح الحفظ.

    إذا بدأت أي جلسة تحضير اليوم تبقى لقطة اليوم ثابتة لحماية التاريخ، بينما
    تستمر شاشة الحصة الحالية في قراءة التوقيت الحي من جدول المدرسة نفسه.
    """

    def publish() -> None:
        from attendance.models import AttendanceDayContext
        from attendance.services.day_context import get_or_refresh_pristine_day_context
        from attendance.services.periods import school_now
        from school_dashboard.cache import invalidate_school
        from schools.models import School

        # لا نحتاج حقول المدرسة هنا؛ تحميل المفتاح فقط يبقي مسار النشر خفيفًا
        # ولا يربطه بأعمدة تعريفية لا علاقة لها بالتوقيت.
        school = School.objects.only("id").get(id=school_id)
        attendance_date = school_now(school).date()
        if AttendanceDayContext.objects.filter(
            school_id=school_id, attendance_date=attendance_date
        ).exists():
            get_or_refresh_pristine_day_context(
                school=school, attendance_date=attendance_date
            )
        invalidate_school(school_id)

    transaction.on_commit(publish)
