from django.db import migrations, models


def without_period_lateness(value):
    if isinstance(value, dict):
        return {
            key: without_period_lateness(item)
            for key, item in value.items()
            if "period_late" not in key.lower()
        }
    if isinstance(value, list):
        return [without_period_lateness(item) for item in value]
    return value


def scrub_period_lateness(apps, schema_editor):
    CounselorCase = apps.get_model("counseling", "CounselorCase")
    FollowUpGoal = apps.get_model("counseling", "FollowUpGoal")

    FollowUpGoal.objects.filter(goal_type="PERIOD_LATENESS").delete()
    for case in CounselorCase.objects.exclude(snapshot_data={}).iterator():
        cleaned = without_period_lateness(case.snapshot_data)
        if cleaned != case.snapshot_data:
            case.snapshot_data = cleaned
            case.save(update_fields=["snapshot_data"])


class Migration(migrations.Migration):
    dependencies = [("counseling", "0001_initial")]

    operations = [
        migrations.RunPython(scrub_period_lateness, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="followupgoal",
            name="goal_type",
            field=models.CharField(
                choices=[
                    ("ATTENDANCE", "المواظبة"),
                    ("MORNING_LATENESS", "التأخر الصباحي"),
                    ("ACADEMIC", "الأداء الدراسي"),
                    ("CLASSROOM_BEHAVIOR", "السلوك الصفي"),
                    ("PARTICIPATION", "المشاركة"),
                    ("CUSTOM", "هدف مخصص"),
                ],
                max_length=24,
            ),
        ),
    ]
