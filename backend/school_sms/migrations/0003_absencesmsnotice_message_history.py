from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("school_sms", "0002_tenant_guards"),
    ]

    operations = [
        migrations.AddField(
            model_name="absencesmsnotice",
            name="message_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="absencesmsnotice",
            name="attempted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
