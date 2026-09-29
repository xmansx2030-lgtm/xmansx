# ruff: noqa: S608

from django.db import migrations


TABLES = ("school_sms_schoolsmsintegration", "school_sms_absencesmsnotice")
TRIGGER = "same_school_sms_notice_student"


def apply_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    guard = (
        "current_setting('app.rls_bypass', true) = 'on' OR "
        "school_id = NULLIF(current_setting('app.current_school_id', true), '')::bigint"
    )
    for table in TABLES:
        policy = f"tenant_isolation_{table}"
        schema_editor.execute(f"ALTER TABLE {quote(table)} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quote(table)} FORCE ROW LEVEL SECURITY")
        schema_editor.execute(
            f"CREATE POLICY {quote(policy)} ON {quote(table)} "
            f"USING ({guard}) WITH CHECK ({guard})"
        )
    schema_editor.execute(
        f"CREATE CONSTRAINT TRIGGER {quote(TRIGGER)} "
        "AFTER INSERT OR UPDATE ON school_sms_absencesmsnotice "
        "DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW "
        "EXECUTE FUNCTION xmansx_enforce_same_school_fk("
        "'public', 'students_student', 'student_id')"
    )


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    schema_editor.execute(
        f"DROP TRIGGER IF EXISTS {quote(TRIGGER)} ON school_sms_absencesmsnotice"
    )
    for table in TABLES:
        policy = f"tenant_isolation_{table}"
        schema_editor.execute(f"DROP POLICY IF EXISTS {quote(policy)} ON {quote(table)}")
        schema_editor.execute(f"ALTER TABLE {quote(table)} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quote(table)} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [
        ("school_sms", "0001_initial"),
        ("operations", "0005_vice_referral_tenant_guards"),
    ]

    operations = [migrations.RunPython(apply_guards, remove_guards)]
