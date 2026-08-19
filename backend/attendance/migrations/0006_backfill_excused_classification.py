"""م10 — تعبئة التصنيف للبيانات السابقة: لا أعذار قبل هذه المرحلة،
فكل غياب قائم «بدون عذر» (excused=0, unexcused=absent_periods).
"""

from django.db import migrations
from django.db.models import F


def backfill_unexcused(apps, schema_editor):
    DailyAttendanceSummary = apps.get_model("attendance", "DailyAttendanceSummary")
    DailyAttendanceSummary.objects.update(
        excused_absent_periods=0, unexcused_absent_periods=F("absent_periods")
    )


def noop(apps, schema_editor):
    pass  # الأعمدة تحذف مع عكس 0005 — لا شيء يعاد هنا


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0005_dailyattendancesummary_excused_absent_periods_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_unexcused, noop),
    ]
