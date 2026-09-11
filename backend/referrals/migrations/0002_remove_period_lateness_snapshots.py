from django.db import migrations


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


def scrub_snapshots(apps, schema_editor):
    StudentReferral = apps.get_model("referrals", "StudentReferral")
    for referral in StudentReferral.objects.exclude(snapshot_data={}).iterator():
        cleaned = without_period_lateness(referral.snapshot_data)
        if cleaned != referral.snapshot_data:
            referral.snapshot_data = cleaned
            referral.save(update_fields=["snapshot_data"])


class Migration(migrations.Migration):
    dependencies = [("referrals", "0001_initial")]

    operations = [
        migrations.RunPython(scrub_snapshots, migrations.RunPython.noop),
    ]
