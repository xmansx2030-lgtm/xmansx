"""Keep original contact evidence and separate private resolution evidence."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("parents", "0003_exact_family_identity_guards")]

    operations = [
        migrations.AddField(
            model_name=model,
            name=name,
            field=models.CharField(blank=True, default="", db_default="", max_length=length),
        )
        for model in ("guardiancontactreview", "recipientcontactblock")
        for name, length in (("resolution_reason", 300), ("resolution_verification_note", 600))
    ]
