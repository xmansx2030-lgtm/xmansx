"""Same-school keys also need an exact child/account match inside one school."""

from django.db import migrations

TABLES = (
    "parents_parentexcuserequest", "parents_attendancecorrectionrequest",
    "parents_parentnotification", "parents_warningacknowledgement",
    "parents_familypublicationacknowledgement", "parents_parentexcuseattachment",
    "parents_familypublication", "parents_guardianactivation",
    "parents_guardianregistrationrequest", "parents_globalmobilechangerequest",
)

SQL = """
CREATE FUNCTION public.xmansx_parent_exact_identity_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
DECLARE rowdata jsonb; relationdata record; referenced_student bigint;
        referenced_user bigint; referenced_request bigint; expected_hash text;
BEGIN
    rowdata := to_jsonb(NEW);
    IF rowdata ? 'relation_id' THEN
        SELECT student_id, user_id, school_id INTO relationdata
        FROM public.parents_guardianstudentrelation WHERE id = (rowdata->>'relation_id')::bigint;
        IF relationdata.school_id IS NULL OR relationdata.school_id <> NEW.school_id
           OR (rowdata ? 'student_id' AND relationdata.student_id <> (rowdata->>'student_id')::bigint)
           OR (rowdata ? 'requester_id' AND relationdata.user_id <> (rowdata->>'requester_id')::bigint)
           OR (rowdata ? 'user_id' AND relationdata.user_id <> (rowdata->>'user_id')::bigint) THEN
            RAISE EXCEPTION 'parent relation identity mismatch' USING ERRCODE = '23514';
        END IF;
        IF TG_TABLE_NAME = 'parents_warningacknowledgement' THEN
            SELECT student_id INTO referenced_student FROM public.student_warnings_studentwarning
            WHERE id = NEW.warning_id AND school_id = NEW.school_id;
            IF referenced_student IS NULL OR referenced_student <> relationdata.student_id THEN
                RAISE EXCEPTION 'parent warning student mismatch' USING ERRCODE = '23514';
            END IF;
        ELSIF TG_TABLE_NAME = 'parents_familypublicationacknowledgement' THEN
            SELECT student_id INTO referenced_student FROM public.parents_familypublication
            WHERE id = NEW.publication_id AND school_id = NEW.school_id;
            IF referenced_student IS NULL OR referenced_student <> relationdata.student_id THEN
                RAISE EXCEPTION 'parent publication student mismatch' USING ERRCODE = '23514';
            END IF;
        ELSIF TG_TABLE_NAME = 'parents_parentexcuserequest'
              AND rowdata->>'administrative_excuse_id' IS NOT NULL THEN
            SELECT student_id INTO referenced_student FROM public.excuses_absenceexcuse
            WHERE id = NEW.administrative_excuse_id AND school_id = NEW.school_id;
            IF referenced_student IS NULL OR referenced_student <> NEW.student_id THEN
                RAISE EXCEPTION 'parent excuse student mismatch' USING ERRCODE = '23514';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'parents_parentexcuseattachment' THEN
        SELECT requester_id INTO referenced_user FROM public.parents_parentexcuserequest
        WHERE id = NEW.parent_request_id AND school_id = NEW.school_id;
        IF referenced_user IS NULL OR referenced_user <> NEW.uploaded_by_id THEN
            RAISE EXCEPTION 'parent attachment owner mismatch' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_TABLE_NAME = 'parents_familypublication' THEN
        IF NEW.case_id IS NOT NULL THEN
            SELECT student_id INTO referenced_student FROM public.counseling_counselorcase
            WHERE id = NEW.case_id AND school_id = NEW.school_id;
            IF referenced_student IS NULL OR referenced_student <> NEW.student_id THEN
                RAISE EXCEPTION 'family case student mismatch' USING ERRCODE = '23514';
            END IF;
        END IF;
        IF NEW.document_id IS NOT NULL THEN
            SELECT student_id INTO referenced_student FROM public.documents_generateddocument
            WHERE id = NEW.document_id AND school_id = NEW.school_id;
            IF referenced_student IS NULL OR referenced_student <> NEW.student_id THEN
                RAISE EXCEPTION 'family document student mismatch' USING ERRCODE = '23514';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'parents_guardianactivation' THEN
        SELECT student_id INTO referenced_student FROM public.parents_guardianregistrationrequest
        WHERE id = NEW.request_id AND school_id = NEW.school_id;
        IF referenced_student IS NULL OR referenced_student <> NEW.student_id THEN
            RAISE EXCEPTION 'activation student mismatch' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_TABLE_NAME = 'parents_guardianregistrationrequest'
          AND rowdata->>'student_id' IS NOT NULL THEN
        SELECT national_id_lookup_hash INTO expected_hash FROM public.students_student
        WHERE id = NEW.student_id AND school_id = NEW.school_id;
        IF expected_hash IS NULL OR expected_hash <> NEW.identifier_hash THEN
            RAISE EXCEPTION 'registration student identity mismatch' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_TABLE_NAME = 'parents_globalmobilechangerequest' THEN
        IF NOT EXISTS (SELECT 1 FROM public.parents_guardianstudentrelation
                       WHERE school_id = NEW.school_id AND student_id = NEW.student_id
                             AND user_id = NEW.user_id) THEN
            RAISE EXCEPTION 'global mobile request guardian mismatch' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""


def apply_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(SQL)
    for table in TABLES:
        schema_editor.execute(
            f"CREATE TRIGGER parent_exact_identity BEFORE INSERT OR UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION public.xmansx_parent_exact_identity_guard()"
        )


def remove_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS parent_exact_identity ON {table}")
    schema_editor.execute("DROP FUNCTION IF EXISTS public.xmansx_parent_exact_identity_guard()")


class Migration(migrations.Migration):
    dependencies = [("parents", "0002_contact_security_and_rls")]
    operations = [migrations.RunPython(apply_guards, remove_guards)]
