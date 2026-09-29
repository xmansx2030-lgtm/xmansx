from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("students", "0004_alter_studentimportrow_status")]

    operations = [
        migrations.AddField(
            model_name="section",
            name="department",
            field=models.CharField("القسم", max_length=100, blank=True, default=""),
        ),
        migrations.RemoveConstraint(
            model_name="section",
            name="uniq_section_code_per_grade",
        ),
        migrations.AddConstraint(
            model_name="section",
            constraint=models.UniqueConstraint(
                fields=["school", "grade", "code", "department"],
                name="uniq_section_code_per_grade",
            ),
        ),
    ]
