from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("staff", "0002_counselorsectionassignment"),
        ("students", "0003_section_qr_token"),
    ]

    operations = [
        migrations.CreateModel(
            name="VicePrincipalScopeAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "grade",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vice_principal_assignments",
                        to="students.grade",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vice_principal_scope_assignments",
                        to="schools.school",
                    ),
                ),
                (
                    "section",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vice_principal_assignments",
                        to="students.section",
                    ),
                ),
                (
                    "vice_principal_membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vice_principal_scope_assignments",
                        to="memberships.schoolmembership",
                    ),
                ),
            ],
            options={
                "verbose_name": "نطاق مسؤولية وكيل",
                "verbose_name_plural": "نطاقات مسؤولية الوكلاء",
                "indexes": [
                    models.Index(
                        fields=["school", "vice_principal_membership"],
                        name="vice_scope_owner_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=(
                            models.Q(grade__isnull=False, section__isnull=True)
                            | models.Q(grade__isnull=True, section__isnull=False)
                        ),
                        name="vice_scope_exactly_one_target",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(grade__isnull=False),
                        fields=("school", "grade"),
                        name="uniq_vice_scope_grade",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(section__isnull=False),
                        fields=("school", "section"),
                        name="uniq_vice_scope_section",
                    ),
                ],
            },
        )
    ]
