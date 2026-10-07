from django.db import migrations


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("ALTER TABLE academics_schoolcalendarpolicy ENABLE ROW LEVEL SECURITY")
    schema_editor.execute("ALTER TABLE academics_schoolcalendarpolicy FORCE ROW LEVEL SECURITY")
    schema_editor.execute(
        "CREATE POLICY tenant_isolation_calendar_policy ON academics_schoolcalendarpolicy "
        "USING (current_setting('app.rls_bypass', true) = 'on' OR "
        "school_id = NULLIF(current_setting('app.current_school_id', true), '')::bigint) "
        "WITH CHECK (current_setting('app.rls_bypass', true) = 'on' OR "
        "school_id = NULLIF(current_setting('app.current_school_id', true), '')::bigint)"
    )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP POLICY IF EXISTS tenant_isolation_calendar_policy ON academics_schoolcalendarpolicy"
    )
    schema_editor.execute("ALTER TABLE academics_schoolcalendarpolicy NO FORCE ROW LEVEL SECURITY")
    schema_editor.execute("ALTER TABLE academics_schoolcalendarpolicy DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [("academics", "0002_ministrycalendarsnapshot_and_more")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
