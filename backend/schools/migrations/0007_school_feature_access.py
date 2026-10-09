from django.db import migrations, models

from schools.feature_defaults import default_feature_access


class Migration(migrations.Migration):
    dependencies = [("schools", "0006_schoolsettings_absence_sms_message_template")]

    operations = [
        # Existing schools retain their contract's feature access. Only schools
        # created after this migration receive the explicit disabled defaults.
        migrations.AddField(
            model_name="school",
            name="feature_access",
            field=models.JSONField(default=dict, verbose_name="تفعيل ميزات المدرسة"),
        ),
        migrations.AlterField(
            model_name="school",
            name="feature_access",
            field=models.JSONField(
                default=default_feature_access, verbose_name="تفعيل ميزات المدرسة"
            ),
        ),
    ]
