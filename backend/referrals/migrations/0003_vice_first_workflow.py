from django.db import migrations, models
import django.db.models.deletion


def migrate_open_referrals(apps, schema_editor):
    StudentReferral = apps.get_model("referrals", "StudentReferral")
    StudentReferral.objects.filter(status="NEW", assigned_counselor_membership__isnull=False).update(
        status="REFERRED"
    )
    StudentReferral.objects.filter(status="NEW", assigned_counselor_membership__isnull=True).update(
        status="PENDING_VICE"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("referrals", "0002_remove_period_lateness_snapshots"),
        ("staff", "0003_viceprincipalscopeassignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentreferral",
            name="assigned_vice_membership",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_vice_referrals",
                to="memberships.schoolmembership",
            ),
        ),
        migrations.AddField(
            model_name="studentreferral",
            name="vice_reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RemoveConstraint(
            model_name="studentreferral",
            name="referral_closed_at_matches_status",
        ),
        migrations.AlterField(
            model_name="studentreferral",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING_VICE", "بانتظار الوكيل"),
                    ("UNDER_VICE_REVIEW", "قيد معالجة الوكيل"),
                    ("REFERRED", "محوّلة للمرشد"),
                    ("ACKNOWLEDGED", "قيد متابعة المرشد"),
                    ("CLOSED", "مغلقة"),
                    ("CANCELLED", "ملغاة"),
                ],
                default="PENDING_VICE",
                max_length=25,
            ),
        ),
        migrations.AlterField(
            model_name="studentreferralevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("CREATED", "أنشئت الإحالة"),
                    ("ROUTED_TO_VICE", "وُجّهت إلى الوكيل المسؤول"),
                    ("VICE_REVIEW_STARTED", "بدأ الوكيل معالجة الإحالة"),
                    ("FORWARDED_TO_COUNSELOR", "حوّلها الوكيل إلى المرشد"),
                    ("ASSIGNED", "تم تعيين مرشد"),
                    ("REASSIGNED", "تم تغيير المرشد"),
                    ("ACKNOWLEDGED", "تم استلام الإحالة"),
                    ("CONTRIBUTION_ADDED", "أضيفت ملاحظة"),
                    ("CLOSED", "أُغلقت الإحالة"),
                    ("CANCELLED", "أُلغيت الإحالة"),
                ],
                max_length=25,
            ),
        ),
        migrations.RunPython(migrate_open_referrals, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="studentreferral",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(status__in=["CLOSED", "CANCELLED"], closed_at__isnull=False)
                    | models.Q(
                        status__in=[
                            "PENDING_VICE",
                            "UNDER_VICE_REVIEW",
                            "REFERRED",
                            "ACKNOWLEDGED",
                        ],
                        closed_at__isnull=True,
                    )
                ),
                name="referral_closed_at_matches_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentreferral",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=["PENDING_VICE", "UNDER_VICE_REVIEW"],
                        assigned_counselor_membership__isnull=True,
                    )
                    | models.Q(
                        status__in=["REFERRED", "ACKNOWLEDGED"],
                        assigned_counselor_membership__isnull=False,
                    )
                    | models.Q(status__in=["CLOSED", "CANCELLED"])
                ),
                name="referral_counselor_matches_stage",
            ),
        ),
        migrations.AddIndex(
            model_name="studentreferral",
            index=models.Index(
                fields=["school", "assigned_vice_membership", "status"],
                name="referral_vice_idx",
            ),
        ),
    ]
