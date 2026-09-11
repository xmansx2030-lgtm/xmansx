from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("student_warnings", "0002_studentwarning_detail_rows_snapshot")]

    operations = [
        migrations.RemoveField(
            model_name="studentwarning",
            name="period_late_occurrences_at_issue",
        ),
        migrations.RemoveField(
            model_name="studentwarning",
            name="period_late_minutes_at_issue",
        ),
    ]
