from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("student_warnings", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="studentwarning",
            name="detail_rows_snapshot",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
