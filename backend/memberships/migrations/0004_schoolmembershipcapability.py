import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("memberships", "0003_alter_schoolmembershiprole_role"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolMembershipCapability",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "capability",
                    models.CharField(
                        choices=[("MORNING_ATTENDANCE", "متابعة التأخر الصباحي")],
                        max_length=40,
                    ),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="capabilities",
                        to="memberships.schoolmembership",
                    ),
                ),
            ],
            options={
                "verbose_name": "تكليف تشغيلي",
                "verbose_name_plural": "التكليفات التشغيلية",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("membership", "capability"),
                        name="uniq_membership_capability",
                    )
                ],
            },
        ),
    ]
