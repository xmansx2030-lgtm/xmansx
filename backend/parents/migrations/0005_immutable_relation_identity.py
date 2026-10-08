"""An approved relation keeps its account and child identity for its lifetime."""

from django.db import migrations


SQL = """
CREATE FUNCTION public.xmansx_parent_relation_identity_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    IF NEW.school_id IS DISTINCT FROM OLD.school_id
       OR NEW.student_id IS DISTINCT FROM OLD.student_id
       OR NEW.user_id IS DISTINCT FROM OLD.user_id THEN
        RAISE EXCEPTION 'guardian relation identity is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER parent_identity_immutable BEFORE UPDATE OF school_id, student_id, user_id
ON public.parents_guardianstudentrelation FOR EACH ROW
EXECUTE FUNCTION public.xmansx_parent_relation_identity_guard();
"""


def apply_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(SQL)


def remove_guard(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "DROP TRIGGER IF EXISTS parent_identity_immutable ON parents_guardianstudentrelation"
        )
        schema_editor.execute(
            "DROP FUNCTION IF EXISTS public.xmansx_parent_relation_identity_guard()"
        )


class Migration(migrations.Migration):
    dependencies = [("parents", "0004_durable_contact_resolution")]
    operations = [migrations.RunPython(apply_guard, remove_guard)]
