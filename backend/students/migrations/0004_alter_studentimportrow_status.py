from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("students", "0003_section_qr_token")]

    operations = [
        migrations.AlterField(
            model_name="studentimportrow",
            name="status",
            field=models.CharField(
                choices=[
                    ("NEW", "جديد"),
                    ("EXISTING_UNCHANGED", "بلا تغيير"),
                    ("EXISTING_UPDATED", "تحديث بيانات"),
                    ("SECTION_CHANGED", "انتقال فصل"),
                    ("GRADE_CHANGED", "تغير صف"),
                    ("ERROR", "خطأ"),
                    ("DUPLICATE_IN_FILE", "مكرر في الملف"),
                    ("AUTO_RESOLVED_DUPLICATE", "تكرار مطابق عولج تلقائيًا"),
                ],
                max_length=30,
            ),
        ),
    ]
