"""Keep baseline Student INSERTs valid while retaining the current contact guard."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("students", "0007_guardian_contact_revision")]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="guardian_contact_revision",
            field=models.PositiveIntegerField(default=1, db_default=1, editable=False),
        )
    ]
