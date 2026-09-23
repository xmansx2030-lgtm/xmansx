from django.db import migrations, models


def infer_existing_contract_durations(apps, schema_editor):
    SchoolSubscription = apps.get_model("subscriptions", "SchoolSubscription")
    for subscription in SchoolSubscription.objects.all().iterator():
        days = max(1, (subscription.ends_at - subscription.starts_at).days)
        if subscription.status == "TRIAL":
            value, unit = subscription.plan.duration_value, subscription.plan.duration_unit
        elif 360 <= days <= 366:
            value, unit = 1, "YEARS"
        elif days % 30 == 0 and days < 360:
            value, unit = max(1, days // 30), "MONTHS"
        else:
            value, unit = days, "DAYS"
        subscription.duration_value = value
        subscription.duration_unit = unit
        subscription.save(update_fields=["duration_value", "duration_unit"])


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="saasplan",
            name="duration_unit",
            field=models.CharField(
                choices=[("DAYS", "أيام"), ("MONTHS", "أشهر"), ("YEARS", "سنوات")],
                default="YEARS",
                max_length=6,
                verbose_name="وحدة مدة الباقة",
            ),
        ),
        migrations.AddField(
            model_name="saasplan",
            name="duration_value",
            field=models.PositiveSmallIntegerField(default=1, verbose_name="قيمة مدة الباقة"),
        ),
        migrations.AddField(
            model_name="schoolsubscription",
            name="duration_unit",
            field=models.CharField(
                choices=[("DAYS", "أيام"), ("MONTHS", "أشهر"), ("YEARS", "سنوات")],
                default="YEARS",
                max_length=6,
            ),
        ),
        migrations.AddField(
            model_name="schoolsubscription",
            name="duration_value",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.RunPython(infer_existing_contract_durations, migrations.RunPython.noop),
    ]
