from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("students", "0006_student_merged_into")]
    operations = [
        migrations.AddField(
            model_name="student",
            name="guardian_contact_revision",
            field=models.PositiveIntegerField(default=1, editable=False),
        ),
    ]
