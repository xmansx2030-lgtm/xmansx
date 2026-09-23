from django.db import migrations, models


def mark_existing_free_subscriptions(apps, schema_editor):
    SchoolSubscription = apps.get_model("subscriptions", "SchoolSubscription")
    SchoolSubscription.objects.filter(plan__price_amount=0).update(was_free_plan=True)


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0002_plan_and_subscription_duration")]

    operations = [
        migrations.AddField(
            model_name="schoolsubscription",
            name="was_free_plan",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_existing_free_subscriptions, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="schoolsubscription",
            index=models.Index(
                fields=["school", "was_free_plan"],
                name="sub_school_free_idx",
            ),
        ),
    ]
