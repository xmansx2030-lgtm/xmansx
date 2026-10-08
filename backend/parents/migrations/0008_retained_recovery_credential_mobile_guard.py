"""Keep the existing global-mobile guard when the last school relation is purged."""

from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION public.xmansx_parent_global_mobile_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE previous_user text; previous_school text; protected boolean;
BEGIN
    IF public.xmansx_parent_mobile_key(OLD.mobile) = public.xmansx_parent_mobile_key(NEW.mobile)
    THEN RETURN NEW; END IF;
    previous_user := COALESCE(current_setting('app.current_user_id', true), '');
    previous_school := COALESCE(current_setting('app.current_school_id', true), '');
    PERFORM set_config('app.current_user_id', OLD.id::text, true);
    PERFORM set_config('app.current_school_id', '', true);
    SELECT EXISTS(SELECT 1 FROM public.parents_guardianstudentrelation WHERE user_id = OLD.id)
        OR EXISTS(SELECT 1 FROM public.parents_accountrecoveryemail WHERE user_id = OLD.id)
    INTO protected;
    PERFORM set_config('app.current_user_id', previous_user, true);
    PERFORM set_config('app.current_school_id', previous_school, true);
    IF protected THEN
        RAISE EXCEPTION 'guardian account mobile requires independent verification'
        USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
"""


REVERSE_SQL = r"""
-- Serialize the empty-data proof with credential inserts/updates until commit.
LOCK TABLE public.parents_accountrecoveryemail,
           public.parents_accountrecoveryemaildelivery IN ACCESS EXCLUSIVE MODE;
DO $$
DECLARE previous_user text; previous_school text; account_id bigint; protected boolean;
BEGIN
    previous_user := COALESCE(current_setting('app.current_user_id', true), '');
    previous_school := COALESCE(current_setting('app.current_school_id', true), '');
    PERFORM set_config('app.current_school_id', '', true);
    -- Exact account scopes also detect retained credentials when the migration
    -- role does not bypass FORCE RLS. Never restore the old guard over real data.
    FOR account_id IN SELECT id FROM public.accounts_user LOOP
        PERFORM set_config('app.current_user_id', account_id::text, true);
        SELECT EXISTS(SELECT 1 FROM public.parents_accountrecoveryemail WHERE user_id = account_id)
            OR EXISTS(SELECT 1 FROM public.parents_accountrecoveryemaildelivery
                      WHERE user_id = account_id)
        INTO protected;
        IF protected THEN
            RAISE EXCEPTION 'recovery credentials require forward fix; unsafe guard rollback blocked'
            USING ERRCODE = '23514';
        END IF;
    END LOOP;
    PERFORM set_config('app.current_user_id', previous_user, true);
    PERFORM set_config('app.current_school_id', previous_school, true);
END;
$$;
CREATE OR REPLACE FUNCTION public.xmansx_parent_global_mobile_guard() RETURNS trigger
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
"""


class Migration(migrations.Migration):
    dependencies = [
        ("parents", "0007_guardianregistrationrequest_email_encrypted_and_more"),
    ]

    operations = [migrations.RunSQL(FORWARD_SQL, reverse_sql=REVERSE_SQL)]
