# ruff: noqa: S608

from django.db import migrations


SCOPE_TABLE = "staff_viceprincipalscopeassignment"
POLICY = "tenant_isolation_staff_viceprincipalscopeassignment"
SCHOOL_SETTING = "NULLIF(current_setting('app.current_school_id', true), '')::bigint"
BYPASS = "current_setting('app.rls_bypass', true) = 'on'"

TRIGGERS = (
    (SCOPE_TABLE, "grade_id", "students_grade"),
    (SCOPE_TABLE, "section_id", "students_section"),
    (SCOPE_TABLE, "vice_principal_membership_id", "memberships_schoolmembership"),
    ("referrals_studentreferral", "assigned_vice_membership_id", "memberships_schoolmembership"),
)


def apply_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    guard = f"{BYPASS} OR school_id = {SCHOOL_SETTING}"
    schema_editor.execute(f"ALTER TABLE {quote(SCOPE_TABLE)} ENABLE ROW LEVEL SECURITY")
    schema_editor.execute(f"ALTER TABLE {quote(SCOPE_TABLE)} FORCE ROW LEVEL SECURITY")
    schema_editor.execute(
        f"CREATE POLICY {quote(POLICY)} ON {quote(SCOPE_TABLE)} "
        f"USING ({guard}) WITH CHECK ({guard})"
    )
    for child_table, fk_column, parent_table in TRIGGERS:
        trigger_name = f"same_school_{child_table}_{fk_column}"[:63]
        # في التثبيت الجديد قد ترى migration 0003 النماذج الأحدث أثناء بناء
        # الرسم الكامل وتكون قد أنشأت الحارس بالفعل؛ أما قواعد الإنتاج
        # المرقّاة فلا تراه. إسقاطه هنا يجعل المسارين حتميين وآمنين.
        schema_editor.execute(
            f"DROP TRIGGER IF EXISTS {quote(trigger_name)} ON {quote(child_table)}"
        )
        schema_editor.execute(
            f"CREATE CONSTRAINT TRIGGER {quote(trigger_name)} "
            f"AFTER INSERT OR UPDATE ON {quote(child_table)} "
            "DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW "
            "EXECUTE FUNCTION xmansx_enforce_same_school_fk("
            f"'public', '{parent_table}', '{fk_column}')"
        )


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    for child_table, fk_column, _parent_table in TRIGGERS:
        trigger_name = f"same_school_{child_table}_{fk_column}"[:63]
        schema_editor.execute(
            f"DROP TRIGGER IF EXISTS {quote(trigger_name)} ON {quote(child_table)}"
        )
    schema_editor.execute(f"DROP POLICY IF EXISTS {quote(POLICY)} ON {quote(SCOPE_TABLE)}")
    schema_editor.execute(f"ALTER TABLE {quote(SCOPE_TABLE)} NO FORCE ROW LEVEL SECURITY")
    schema_editor.execute(f"ALTER TABLE {quote(SCOPE_TABLE)} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0004_protect_memberships_and_global_audit"),
        ("staff", "0003_viceprincipalscopeassignment"),
        ("referrals", "0003_vice_first_workflow"),
    ]

    operations = [migrations.RunPython(apply_guards, remove_guards)]
