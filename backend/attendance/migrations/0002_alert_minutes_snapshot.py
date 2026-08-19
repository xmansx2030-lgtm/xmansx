# توليد يدوي (م7): snapshot مهلة التنبيه على الجلسات.
# الجلسات القائمة (dev/test فقط — لا إنتاج بعد) تعبأ من إعدادات مدرستها الحالية،
# وهو أفضل تقريب متاح تاريخيًا؛ default=25 احتياط لمدرسة بلا صف إعدادات.

from django.db import migrations, models


def fill_snapshot(apps, schema_editor):
    AttendanceSession = apps.get_model("attendance", "AttendanceSession")
    SchoolSettings = apps.get_model("schools", "SchoolSettings")
    minutes_by_school = dict(
        SchoolSettings.objects.values_list("school_id", "unprepared_period_alert_minutes")
    )
    to_update = []
    for session in AttendanceSession.objects.filter(
        unprepared_alert_minutes_snapshot__isnull=True
    ).only("id", "school_id"):
        session.unprepared_alert_minutes_snapshot = minutes_by_school.get(
            session.school_id, 25
        )
        to_update.append(session)
    AttendanceSession.objects.bulk_update(
        to_update, ["unprepared_alert_minutes_snapshot"], batch_size=500
    )


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0001_initial"),
        ("schools", "0002_schoolsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendancesession",
            name="unprepared_alert_minutes_snapshot",
            field=models.PositiveSmallIntegerField(null=True),
        ),
        migrations.RunPython(fill_snapshot, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="attendancesession",
            name="unprepared_alert_minutes_snapshot",
            field=models.PositiveSmallIntegerField(),
        ),
    ]
