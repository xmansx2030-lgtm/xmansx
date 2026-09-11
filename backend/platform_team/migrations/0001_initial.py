import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="PlatformStaffMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("role", models.CharField(choices=[("OPERATIONS_MANAGER", "مدير العمليات"), ("SUPPORT", "خدمة المدارس"), ("BILLING", "الاشتراكات والفوترة"), ("AUDITOR", "مراجع")], max_length=30)),
                ("status", models.CharField(choices=[("ACTIVE", "نشط"), ("SUSPENDED", "موقوف")], default="ACTIVE", max_length=20)),
                ("job_title", models.CharField(blank=True, default="", max_length=120)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="platform_staff_created", to=settings.AUTH_USER_MODEL)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="platform_staff_membership", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "موظف منصة",
                "verbose_name_plural": "موظفو المنصة",
                "indexes": [models.Index(fields=["status", "role"], name="platform_staff_status_role_idx")],
            },
        )
    ]
