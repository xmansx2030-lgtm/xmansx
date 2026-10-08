# ruff: noqa: S608
"""Fail-closed tenancy and transaction-atomic contact lifecycle enforcement."""

from django.core.exceptions import FieldDoesNotExist
from django.db import migrations

SCHOOL = "NULLIF(current_setting('app.current_school_id', true), '')::bigint"
USER = "NULLIF(current_setting('app.current_user_id', true), '')::bigint"
BYPASS = "current_setting('app.rls_bypass', true) = 'on'"

CONTACT_SQL = r"""
CREATE FUNCTION public.xmansx_parent_mobile_key(raw text) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog AS $$
DECLARE value text; digits text; rest text;
BEGIN
    value := translate(regexp_replace(btrim(COALESCE(raw, '')), '[\s().-]', '', 'g'),
                       '٠١٢٣٤٥٦٧٨٩', '0123456789');
    IF value = '' THEN RETURN ''; END IF;
    IF left(value, 1) = '+' THEN digits := substr(value, 2);
    ELSIF left(value, 2) = '00' THEN digits := substr(value, 3);
    ELSE digits := value; END IF;
    IF digits !~ '^[0-9]+$' THEN RETURN 'invalid:' || btrim(COALESCE(raw, '')); END IF;
    IF left(digits, 3) = '966' THEN rest := substr(digits, 4);
    ELSIF left(digits, 2) = '05' THEN rest := substr(digits, 2);
    ELSIF left(digits, 1) = '5' THEN rest := digits;
    ELSE RETURN 'invalid:' || btrim(COALESCE(raw, '')); END IF;
    IF rest ~ '^5[0-9]{8}$' THEN RETURN '+966' || rest; END IF;
    RETURN 'invalid:' || btrim(COALESCE(raw, ''));
END;
$$;

CREATE FUNCTION public.xmansx_parent_contact_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE old_name text; new_name text; old_mobile text; new_mobile text;
        source text; actor bigint; reason text;
BEGIN
    IF NEW.school_id <> OLD.school_id THEN
        RAISE EXCEPTION 'student school is immutable' USING ERRCODE = '23514';
    END IF;
    old_name := lower(btrim(regexp_replace(translate(normalize(OLD.guardian_name, NFKC),
                                                    '​‌‍‎‏﻿', ''), '\s+', ' ', 'g')));
    new_name := lower(btrim(regexp_replace(translate(normalize(NEW.guardian_name, NFKC),
                                                    '​‌‍‎‏﻿', ''), '\s+', ' ', 'g')));
    old_mobile := public.xmansx_parent_mobile_key(OLD.guardian_mobile);
    new_mobile := public.xmansx_parent_mobile_key(NEW.guardian_mobile);
    NEW.guardian_contact_revision := OLD.guardian_contact_revision;
    IF new_mobile = old_mobile AND old_name = new_name THEN
        RETURN NEW;
    END IF;
    NEW.guardian_contact_revision := OLD.guardian_contact_revision + 1;
    source := COALESCE(NULLIF(current_setting('app.parent_contact_source', true), ''), 'DATABASE');
    actor := NULLIF(current_setting('app.parent_contact_actor', true), '')::bigint;
    IF actor IS NULL THEN actor := NULLIF(current_setting('app.current_user_id', true), '')::bigint; END IF;
    reason := COALESCE(current_setting('app.parent_contact_reason', true), '');
    WITH suspended AS (
        UPDATE public.parents_guardianstudentrelation
        SET status = 'SUSPENDED_CONTACT_REVIEW', suspended_at = statement_timestamp(),
            suspension_reason = 'تغيرت بيانات التواصل المدرسي وتحتاج إلى مراجعة.',
            updated_at = statement_timestamp()
        WHERE school_id = OLD.school_id AND student_id = OLD.id
              AND contact_bound AND status = 'ACTIVE'
        RETURNING id, user_id, school_id
    )
    INSERT INTO public.parents_parentnotification
        (created_at, updated_at, school_id, relation_id, user_id, kind, dedup_key,
         title, body, requires_action, read_at, action_completed_at)
    SELECT statement_timestamp(), statement_timestamp(), school_id, id, user_id,
           'RELATION_STATUS', 'contact-review:' || NEW.guardian_contact_revision,
           'تحتاج علاقة الطالب إلى مراجعة',
           'أوقف الوصول مؤقتاً لمراجعة بيانات التواصل.', true, NULL, NULL
    FROM suspended ON CONFLICT (relation_id, dedup_key) DO NOTHING;

    UPDATE public.parents_guardianactivation activation
    SET revoked_at = statement_timestamp(), updated_at = statement_timestamp()
    WHERE activation.school_id = OLD.school_id AND activation.student_id = OLD.id
          AND activation.used_at IS NULL AND activation.revoked_at IS NULL
          AND EXISTS (SELECT 1 FROM public.parents_guardianregistrationrequest request
                      WHERE request.id = activation.request_id AND request.contact_bound);
    UPDATE public.parents_guardianregistrationrequest
    SET status = 'NEEDS_INFO', decision_reason = 'تغيرت بيانات التواصل؛ يلزم اعتماد جديد.',
        updated_at = statement_timestamp()
    WHERE school_id = OLD.school_id AND student_id = OLD.id AND contact_bound AND status = 'APPROVED';
    INSERT INTO public.parents_guardiancontactreview
        (created_at, updated_at, school_id, student_id, previous_revision, current_revision,
         source, actor_id, reason, previous_mobile_hash, current_mobile_hash,
         resolved_at, resolved_by_id, verification_note)
    VALUES (statement_timestamp(), statement_timestamp(), OLD.school_id, OLD.id,
            OLD.guardian_contact_revision, NEW.guardian_contact_revision,
            left(source, 40), actor, left(reason, 300),
            COALESCE(current_setting('app.parent_previous_contact_hash', true), ''),
            COALESCE(current_setting('app.parent_current_contact_hash', true), ''),
            NULL, NULL, '');
    INSERT INTO public.audit_auditlog
        (school_id, actor_id, action, target_type, target_id, metadata,
         request_id, ip_address, user_agent, created_at)
    VALUES (OLD.school_id, actor, 'PARENT_CONTACT_CHANGED', 'Student', OLD.id::text,
            jsonb_build_object('source', left(source, 40),
                               'previous_revision', OLD.guardian_contact_revision,
                               'current_revision', NEW.guardian_contact_revision),
            '', NULL, '', statement_timestamp());
    RETURN NEW;
END;
$$;
CREATE TRIGGER parent_contact_guard BEFORE UPDATE ON public.students_student
FOR EACH ROW EXECUTE FUNCTION public.xmansx_parent_contact_guard();

CREATE FUNCTION public.xmansx_parent_global_mobile_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE previous_user text; protected boolean;
BEGIN
    IF public.xmansx_parent_mobile_key(OLD.mobile) = public.xmansx_parent_mobile_key(NEW.mobile)
    THEN RETURN NEW; END IF;
    previous_user := COALESCE(current_setting('app.current_user_id', true), '');
    PERFORM set_config('app.current_user_id', OLD.id::text, true);
    SELECT EXISTS(SELECT 1 FROM public.parents_guardianstudentrelation WHERE user_id = OLD.id)
    INTO protected;
    PERFORM set_config('app.current_user_id', previous_user, true);
    IF protected THEN
        RAISE EXCEPTION 'guardian account mobile requires independent verification'
        USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER parent_global_mobile_guard BEFORE UPDATE OF mobile ON public.accounts_user
FOR EACH ROW EXECUTE FUNCTION public.xmansx_parent_global_mobile_guard();

CREATE FUNCTION public.xmansx_parent_relation_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE revision integer;
BEGIN
    IF NEW.status = 'ACTIVE' THEN
        SELECT guardian_contact_revision INTO revision FROM public.students_student
        WHERE id = NEW.student_id AND school_id = NEW.school_id FOR UPDATE;
        IF revision IS NULL OR NEW.approved_at IS NULL OR NEW.approved_by_id IS NULL
           OR (NEW.contact_bound AND NEW.contact_revision <> revision) THEN
            RAISE EXCEPTION 'guardian relation requires current school approval'
            USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER parent_relation_guard BEFORE INSERT OR UPDATE
ON public.parents_guardianstudentrelation FOR EACH ROW
EXECUTE FUNCTION public.xmansx_parent_relation_guard();
"""


def _models(apps):
    return [model for model in apps.get_app_config("parents").get_models()
            if any(field.name == "school" for field in model._meta.fields)]


def apply_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    quote = schema_editor.quote_name
    for model in _models(apps):
        table = model._meta.db_table
        scope = f"{BYPASS} OR school_id = {SCHOOL}"
        select = scope
        if table == "parents_guardianstudentrelation":
            select += f" OR user_id = {USER}"
        elif table == "parents_parentregistrationconfig":
            select = "true"
        elif table == "parents_guardianactivation":
            select += " OR token_hash = NULLIF(current_setting('app.parent_activation_hash', true), '')"
        elif table == "parents_guardianregistrationrequest":
            select += " OR receipt_hash = NULLIF(current_setting('app.parent_receipt_hash', true), '')"
        elif table == "parents_parentnotification":
            select += f" OR user_id = {USER}"
        schema_editor.execute(f"ALTER TABLE {quote(table)} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quote(table)} FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"CREATE POLICY parent_select ON {quote(table)} FOR SELECT USING ({select})")
        schema_editor.execute(f"CREATE POLICY parent_insert ON {quote(table)} FOR INSERT WITH CHECK ({scope})")
        schema_editor.execute(f"CREATE POLICY parent_update ON {quote(table)} FOR UPDATE USING ({scope}) WITH CHECK ({scope})")
        schema_editor.execute(f"CREATE POLICY parent_delete ON {quote(table)} FOR DELETE USING ({scope})")
        for field in model._meta.fields:
            if not field.many_to_one or field.related_model is None:
                continue
            try:
                field.related_model._meta.get_field("school")
            except FieldDoesNotExist:
                continue
            trigger = f"same_school_{table}_{field.column}"[:63]
            schema_editor.execute(
                f"CREATE CONSTRAINT TRIGGER {quote(trigger)} AFTER INSERT OR UPDATE ON {quote(table)} "
                "DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW "
                "EXECUTE FUNCTION public.xmansx_enforce_same_school_fk("
                f"'public', '{field.related_model._meta.db_table}', '{field.column}')"
            )
    schema_editor.execute(CONTACT_SQL)


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS parent_relation_guard ON parents_guardianstudentrelation")
    schema_editor.execute("DROP TRIGGER IF EXISTS parent_global_mobile_guard ON accounts_user")
    schema_editor.execute("DROP TRIGGER IF EXISTS parent_contact_guard ON students_student")
    for function in ("xmansx_parent_relation_guard()", "xmansx_parent_global_mobile_guard()",
                     "xmansx_parent_contact_guard()", "xmansx_parent_mobile_key(text)"):
        schema_editor.execute(f"DROP FUNCTION IF EXISTS public.{function}")
    quote = schema_editor.quote_name
    for model in _models(apps):
        table = model._meta.db_table
        for field in model._meta.fields:
            if not field.many_to_one or field.related_model is None:
                continue
            try:
                field.related_model._meta.get_field("school")
            except FieldDoesNotExist:
                continue
            trigger = f"same_school_{table}_{field.column}"[:63]
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {quote(trigger)} ON {quote(table)}")
        for policy in ("parent_select", "parent_insert", "parent_update", "parent_delete"):
            schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {quote(table)}")
        schema_editor.execute(f"ALTER TABLE {quote(table)} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quote(table)} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [("parents", "0001_initial"), ("students", "0007_guardian_contact_revision"),
                    ("operations", "0006_allow_scoped_school_audit_purge")]
    operations = [migrations.RunPython(apply_guards, remove_guards)]
