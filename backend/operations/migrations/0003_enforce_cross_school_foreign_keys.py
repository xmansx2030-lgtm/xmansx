# ruff: noqa: S608

from django.core.exceptions import FieldDoesNotExist
from django.db import migrations

TENANT_APP_LABELS = {
    "academics",
    "attendance",
    "audit",
    "counseling",
    "devices",
    "documents",
    "excuses",
    "memberships",
    "referrals",
    "schools",
    "staff",
    "student_actions",
    "student_leaves",
    "student_warnings",
    "students",
    "subscriptions",
}

FUNCTION_NAME = "xmansx_enforce_same_school_fk"


def _tenant_relationships(apps):
    for model in apps.get_models():
        if model._meta.app_label not in TENANT_APP_LABELS:
            continue
        try:
            model._meta.get_field("school")
        except FieldDoesNotExist:
            continue
        for field in model._meta.fields:
            if not field.is_relation or not field.many_to_one or field.related_model is None:
                continue
            try:
                field.related_model._meta.get_field("school")
            except FieldDoesNotExist:
                continue
            yield model._meta.db_table, field.column, field.related_model._meta.db_table


def enforce_same_school_foreign_keys(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    schema_editor.execute("SELECT set_config('app.rls_bypass', 'on', true)")
    schema_editor.execute(
        f"""
        CREATE FUNCTION {quote(FUNCTION_NAME)}() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
        DECLARE
            referenced_school_id bigint;
            foreign_key_id bigint;
        BEGIN
            foreign_key_id := NULLIF(to_jsonb(NEW)->>TG_ARGV[2], '')::bigint;
            IF foreign_key_id IS NULL THEN
                RETURN NEW;
            END IF;
            EXECUTE format(
                'SELECT school_id FROM %%I.%%I WHERE id = $1', TG_ARGV[0], TG_ARGV[1]
            ) INTO referenced_school_id USING foreign_key_id;
            IF referenced_school_id IS NULL OR referenced_school_id <> NEW.school_id THEN
                RAISE EXCEPTION 'cross-school foreign key rejected on %%.%%',
                    TG_TABLE_NAME, TG_ARGV[2]
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for child_table, fk_column, parent_table in _tenant_relationships(apps):
        mismatch_sql = (
            f"SELECT 1 FROM {quote(child_table)} child "
            f"JOIN {quote(parent_table)} parent ON parent.id = child.{quote(fk_column)} "
            f"WHERE child.{quote(fk_column)} IS NOT NULL "
            "AND child.school_id <> parent.school_id LIMIT 1"
        )
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(mismatch_sql)
            mismatch = cursor.fetchone()
        if mismatch:
            raise RuntimeError(
                f"Existing cross-school relationship: {child_table}.{fk_column}"
            )
        trigger_name = f"same_school_{child_table}_{fk_column}"[:63]
        schema_editor.execute(
            f"CREATE CONSTRAINT TRIGGER {quote(trigger_name)} "
            f"AFTER INSERT OR UPDATE ON {quote(child_table)} "
            "DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW "
            f"EXECUTE FUNCTION {quote(FUNCTION_NAME)}("
            f"'public', '{parent_table}', '{fk_column}')"
        )
    schema_editor.execute("SELECT set_config('app.rls_bypass', 'off', true)")


def remove_same_school_foreign_keys(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    for child_table, fk_column, _parent_table in _tenant_relationships(apps):
        trigger_name = f"same_school_{child_table}_{fk_column}"[:63]
        schema_editor.execute(
            f"DROP TRIGGER IF EXISTS {quote(trigger_name)} ON {quote(child_table)}"
        )
    schema_editor.execute(f"DROP FUNCTION IF EXISTS {quote(FUNCTION_NAME)}()")


class Migration(migrations.Migration):
    dependencies = [("operations", "0002_strict_tenant_row_level_security")]

    operations = [
        migrations.RunPython(
            enforce_same_school_foreign_keys,
            remove_same_school_foreign_keys,
        )
    ]
