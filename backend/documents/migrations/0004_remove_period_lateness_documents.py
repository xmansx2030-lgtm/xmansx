from django.db import migrations, models

PERIOD_DOCUMENT_TYPE = "PERIOD_LATE_DETAIL_REPORT"


def _without_period_lateness(value):
    if isinstance(value, dict):
        return {
            key: _without_period_lateness(item)
            for key, item in value.items()
            if "period_late" not in key.lower()
        }
    if isinstance(value, list):
        return [_without_period_lateness(item) for item in value]
    return value


def purge_period_lateness_documents(apps, schema_editor):
    GeneratedDocument = apps.get_model("documents", "GeneratedDocument")
    storage = GeneratedDocument._meta.get_field("file").storage

    removed = GeneratedDocument.objects.filter(document_type=PERIOD_DOCUMENT_TYPE)
    for document in removed.iterator():
        if document.file:
            storage.delete(document.file.name)
    removed.delete()

    for document in GeneratedDocument.objects.exclude(snapshot_data={}).iterator():
        cleaned = _without_period_lateness(document.snapshot_data)
        if cleaned != document.snapshot_data:
            document.snapshot_data = cleaned
            document.save(update_fields=["snapshot_data"])


class Migration(migrations.Migration):
    dependencies = [("documents", "0003_alter_generateddocument_snapshot_schema_version")]

    operations = [
        migrations.RunPython(
            purge_period_lateness_documents,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="generateddocument",
            name="document_type",
            field=models.CharField(
                choices=[
                    ("WARNING_LEVEL_1", "الإنذار الأول"),
                    ("WARNING_LEVEL_2", "الإنذار الثاني"),
                    ("WARNING_LEVEL_3", "الإنذار الثالث"),
                    ("ATTENDANCE_COMMITMENT", "تعهد الالتزام بالحضور"),
                    ("ABSENCE_DETAIL_REPORT", "كشف تفصيلي للغياب"),
                    ("MORNING_LATE_DETAIL_REPORT", "كشف تفصيلي للتأخر الصباحي"),
                    ("STUDENT_ATTENDANCE_REPORT", "تقرير مواظبة الطالب"),
                ],
                max_length=32,
            ),
        ),
    ]
