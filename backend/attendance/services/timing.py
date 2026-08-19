"""حسابات مهلة التنبيه (م7) — مصدر الحقيقة الوحيد لسياسة الحدود والتقريب.

السياسات الموثقة:
- Boundary: ‏`at >= alert_at` يعني OVERDUE (‏08:54:59 في الوقت، 08:55:00 متأخر).
- التقريب: ‏floor لإجمالي الدقائق المنقضية بعد alert_at — ‏08:55→09:02 = 7 دقائق،
  و08:55:00 نفسها = 0 دقائق (متأخر بلا دقيقة كاملة بعد). الواجهة تعرض القيم كما
  تصلها ولا تعيد الحساب.
- جلسة قائمة (IN_PROGRESS/SUBMITTED): البداية من bell_period_snapshot والمهلة من
  unprepared_alert_minutes_snapshot — تغيير الإعداد لاحقًا لا يمس جلسات قائمة.
- فصل بلا جلسة (NOT_STARTED): لا snapshot يثبت شيئًا — الإعداد الحالي هو المرجع.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from attendance.models import AttendanceSession


def alert_at_for(
    *, day: date, start_time: time, alert_minutes: int, tz_name: str
) -> datetime:
    """لحظة التنبيه (aware): بداية الحصة + المهلة، بمنطقة المدرسة الزمنية."""
    start = datetime.combine(day, start_time, tzinfo=ZoneInfo(tz_name))
    return start + timedelta(minutes=alert_minutes)


def overdue_minutes(alert_at: datetime, at: datetime) -> int | None:
    """None = في الوقت؛ وإلا دقائق التجاوز (floor). الحد: at >= alert_at متأخر."""
    if at < alert_at:
        return None
    return int((at - alert_at).total_seconds() // 60)


def session_alert_at(session: AttendanceSession) -> datetime:
    """لحظة التنبيه لجلسة قائمة — من الـ snapshots حصرًا (تاريخ ثابت)."""
    snapshot = session.bell_period_snapshot
    hour, minute = (int(p) for p in snapshot["start_time"].split(":"))
    return alert_at_for(
        day=session.attendance_date,
        start_time=time(hour, minute),
        alert_minutes=session.unprepared_alert_minutes_snapshot,
        tz_name=snapshot["timezone"],
    )


def session_submission_delay_minutes(session: AttendanceSession) -> int | None:
    """دقائق تأخر الاعتماد وفق الـ snapshots — None إن لم تعتمد أو اعتمدت في الوقت.

    يعتمد على submitted_at «أول اعتماد نهائي» الثابت — التعديلات اللاحقة تسجل في
    AttendanceChange ولا تمسه، فقياس الالتزام التاريخي لا يتغير.
    """
    if session.submitted_at is None:
        return None
    return overdue_minutes(session_alert_at(session), session.submitted_at)
