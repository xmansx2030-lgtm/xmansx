from django.db import migrations, models
from django.db.models import F, Q


def purge_period_lateness(apps, schema_editor):
    AttendanceChange = apps.get_model("attendance", "AttendanceChange")
    AttendanceMark = apps.get_model("attendance", "AttendanceMark")
    DailyAttendanceSummary = apps.get_model("attendance", "DailyAttendanceSummary")

    AttendanceChange.objects.filter(
        Q(previous_status="LATE") | Q(new_status="LATE")
    ).delete()
    AttendanceMark.objects.filter(status="LATE").delete()
    DailyAttendanceSummary.objects.update(
        present_periods=F("submitted_periods") - F("absent_periods")
    )


class Migration(migrations.Migration):
    dependencies = [("attendance", "0006_backfill_excused_classification")]

    operations = [
        migrations.RunPython(purge_period_lateness, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="attendancechange",
            name="new_late_minutes",
        ),
        migrations.RemoveField(
            model_name="attendancechange",
            name="previous_late_minutes",
        ),
        migrations.RemoveField(
            model_name="attendancemark",
            name="arrival_time",
        ),
        migrations.RemoveField(
            model_name="attendancemark",
            name="late_minutes",
        ),
        migrations.AlterField(
            model_name="attendancemark",
            name="status",
            field=models.CharField(choices=[("ABSENT", "غائب")], max_length=10),
        ),
        migrations.RemoveField(
            model_name="dailyattendancesummary",
            name="late_periods",
        ),
        migrations.RemoveField(
            model_name="dailyattendancesummary",
            name="total_late_minutes",
        ),
    ]
