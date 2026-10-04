from django.db import migrations


def allow_scoped_purge(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE POLICY audit_school_purge_delete ON audit_auditlog FOR DELETE USING ("
        "current_setting('app.rls_bypass', true) = 'on' AND "
        "school_id = NULLIF(current_setting('app.school_purge_id', true), '')::bigint)"
    )


def disallow_scoped_purge(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP POLICY IF EXISTS audit_school_purge_delete ON audit_auditlog")


class Migration(migrations.Migration):
    dependencies = [("operations", "0005_vice_referral_tenant_guards")]

    operations = [migrations.RunPython(allow_scoped_purge, disallow_scoped_purge)]
