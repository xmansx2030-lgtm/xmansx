# ruff: noqa: S608

from django.db import migrations

POLICY_PREFIX = "current_setting('app.rls_bypass', true) = 'on'"
SCHOOL_SETTING = "NULLIF(current_setting('app.current_school_id', true), '')::bigint"
USER_SETTING = "NULLIF(current_setting('app.current_user_id', true), '')::bigint"


def apply_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    statements = [
        "DROP POLICY tenant_isolation_audit_auditlog ON audit_auditlog",
        "CREATE POLICY audit_tenant_select ON audit_auditlog FOR SELECT USING "
        f"({POLICY_PREFIX} OR school_id = {SCHOOL_SETTING})",
        "CREATE POLICY audit_tenant_insert ON audit_auditlog FOR INSERT WITH CHECK "
        f"({POLICY_PREFIX} OR school_id IS NULL OR school_id = {SCHOOL_SETTING})",
        "ALTER TABLE memberships_schoolmembership ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE memberships_schoolmembership FORCE ROW LEVEL SECURITY",
        "CREATE POLICY membership_self_select ON memberships_schoolmembership FOR SELECT USING "
        f"({POLICY_PREFIX} OR user_id = {USER_SETTING} "
        f"OR school_id = {SCHOOL_SETTING})",
        "CREATE POLICY membership_tenant_write ON memberships_schoolmembership FOR ALL USING "
        f"({POLICY_PREFIX} OR school_id = {SCHOOL_SETTING}) "
        "WITH CHECK "
        f"({POLICY_PREFIX} OR school_id = {SCHOOL_SETTING})",
        "ALTER TABLE schools_school ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE schools_school FORCE ROW LEVEL SECURITY",
        "CREATE POLICY school_tenant_select ON schools_school FOR SELECT USING ("
        f"{POLICY_PREFIX} OR id = {SCHOOL_SETTING} OR EXISTS ("
        "SELECT 1 FROM memberships_schoolmembership membership "
        "WHERE membership.school_id = schools_school.id "
        f"AND membership.user_id = {USER_SETTING}))",
        "CREATE POLICY school_tenant_write ON schools_school FOR ALL USING "
        f"({POLICY_PREFIX} OR id = {SCHOOL_SETTING}) WITH CHECK "
        f"({POLICY_PREFIX} OR id = {SCHOOL_SETTING})",
    ]
    for table in (
        "memberships_schoolmembershiprole",
        "memberships_schoolmembershipcapability",
    ):
        statements.extend(
            [
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
                f"CREATE POLICY membership_child_self_select ON {table} FOR SELECT USING ("
                f"{POLICY_PREFIX} OR EXISTS (SELECT 1 FROM memberships_schoolmembership parent "
                "WHERE parent.id = membership_id AND ("
                f"parent.user_id = {USER_SETTING} "
                f"OR parent.school_id = {SCHOOL_SETTING})))",
                f"CREATE POLICY membership_child_tenant_write ON {table} FOR ALL USING ("
                f"{POLICY_PREFIX} OR EXISTS (SELECT 1 FROM memberships_schoolmembership parent "
                f"WHERE parent.id = membership_id AND parent.school_id = {SCHOOL_SETTING})) "
                "WITH CHECK ("
                f"{POLICY_PREFIX} OR EXISTS (SELECT 1 FROM memberships_schoolmembership parent "
                f"WHERE parent.id = membership_id AND parent.school_id = {SCHOOL_SETTING}))",
            ]
        )
    for statement in statements:
        schema_editor.execute(statement)


def remove_policies(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP POLICY IF EXISTS audit_tenant_select ON audit_auditlog")
    schema_editor.execute("DROP POLICY IF EXISTS audit_tenant_insert ON audit_auditlog")
    guard = (
        f"{POLICY_PREFIX} OR school_id = "
        f"{SCHOOL_SETTING}"
    )
    schema_editor.execute(
        "CREATE POLICY tenant_isolation_audit_auditlog ON audit_auditlog "
        f"USING ({guard}) WITH CHECK ({guard})"
    )
    for table in (
        "memberships_schoolmembershiprole",
        "memberships_schoolmembershipcapability",
    ):
        schema_editor.execute(
            f"DROP POLICY IF EXISTS membership_child_self_select ON {table}"
        )
        schema_editor.execute(
            f"DROP POLICY IF EXISTS membership_child_tenant_write ON {table}"
        )
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    schema_editor.execute(
        "DROP POLICY IF EXISTS membership_self_select ON memberships_schoolmembership"
    )
    schema_editor.execute(
        "DROP POLICY IF EXISTS membership_tenant_write ON memberships_schoolmembership"
    )
    schema_editor.execute("DROP POLICY IF EXISTS school_tenant_select ON schools_school")
    schema_editor.execute("DROP POLICY IF EXISTS school_tenant_write ON schools_school")
    schema_editor.execute("ALTER TABLE schools_school NO FORCE ROW LEVEL SECURITY")
    schema_editor.execute("ALTER TABLE schools_school DISABLE ROW LEVEL SECURITY")
    schema_editor.execute(
        "ALTER TABLE memberships_schoolmembership NO FORCE ROW LEVEL SECURITY"
    )
    schema_editor.execute(
        "ALTER TABLE memberships_schoolmembership DISABLE ROW LEVEL SECURITY"
    )


class Migration(migrations.Migration):
    dependencies = [("operations", "0003_enforce_cross_school_foreign_keys")]

    operations = [migrations.RunPython(apply_policies, remove_policies)]
