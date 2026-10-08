"""Add an exact activation-email proof; keep the existing global credential guard."""

import importlib
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def original_email_guard():
    module = importlib.import_module(
        "parents.migrations.0007_guardianregistrationrequest_email_encrypted_and_more"
    )
    return module.GUARD_SQL.split("CREATE TRIGGER parent_email_guard", 1)[0].replace(
        "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1,
    )


ACTIVATION_PROOF = r"""
 IF action = 'ACTIVATE' THEN
   SELECT a.* INTO proof FROM public.parents_guardianactivation a
   WHERE a.token_hash=NULLIF(current_setting('app.parent_activation_hash',true),'')
     AND a.delivery_channel='EMAIL' AND a.activated_user_id=actor
     AND a.used_at IS NOT NULL AND a.revoked_at IS NULL
     AND a.expires_at>statement_timestamp()
     AND a.delivery_status IN ('SENDING','SENT','UNKNOWN');
   IF proof.id IS NULL OR OLD.verified_at IS NOT NULL
      OR proof.email_hash<>OLD.pending_email_hash
      OR NEW.current_email_hash IS DISTINCT FROM OLD.pending_email_hash
      OR NEW.current_email_encrypted IS DISTINCT FROM OLD.pending_email_encrypted
      OR NEW.verified_at IS NULL OR NEW.revision<>OLD.revision+1
      OR NEW.pending_revision<>OLD.pending_revision
      OR NEW.pending_email_hash<>'' OR NEW.pending_email_encrypted<>'' THEN
     RAISE EXCEPTION 'email activation requires its consumed exact account bearer'
       USING ERRCODE='23514';
   END IF;
   RETURN NEW;
 END IF;
"""

ACTIVATION_GUARD = r"""
CREATE FUNCTION public.xmansx_parent_activation_email_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE request_email text;
BEGIN
 IF TG_OP='INSERT' THEN
   IF NEW.delivery_channel='EMAIL' THEN
     SELECT email_hash INTO request_email FROM public.parents_guardianregistrationrequest
       WHERE id=NEW.request_id AND school_id=NEW.school_id AND status='APPROVED';
     IF request_email IS NULL OR request_email='' OR NEW.email_hash<>request_email
        OR NEW.used_at IS NOT NULL OR NEW.activated_user_id IS NOT NULL THEN
       RAISE EXCEPTION 'email activation approval binding mismatch' USING ERRCODE='23514';
     END IF;
   END IF;
   RETURN NEW;
 END IF;
 IF NEW.delivery_channel<>OLD.delivery_channel OR NEW.email_hash<>OLD.email_hash
    OR NEW.delivery_key IS DISTINCT FROM OLD.delivery_key
    OR NEW.school_id<>OLD.school_id OR NEW.student_id<>OLD.student_id
    OR NEW.request_id<>OLD.request_id
    OR (OLD.delivery_channel='EMAIL' AND NEW.expires_at IS DISTINCT FROM OLD.expires_at) THEN
   RAISE EXCEPTION 'activation email binding is immutable' USING ERRCODE='23514';
 END IF;
 IF OLD.delivery_channel<>'EMAIL' THEN RETURN NEW; END IF;
 IF OLD.used_at IS NOT NULL AND (NEW.used_at IS DISTINCT FROM OLD.used_at
    OR NEW.activated_user_id IS DISTINCT FROM OLD.activated_user_id)
    OR OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS DISTINCT FROM OLD.revoked_at THEN
   RAISE EXCEPTION 'email activation cannot be replayed' USING ERRCODE='23514';
 END IF;
 IF NEW.token_hash IS DISTINCT FROM OLD.token_hash THEN
   IF current_setting('app.parent_activation_delivery_id',true) IS DISTINCT FROM OLD.id::text
      OR OLD.delivery_status<>'PENDING' OR NEW.delivery_status<>'SENDING'
      OR OLD.used_at IS NOT NULL OR OLD.revoked_at IS NOT NULL THEN
     RAISE EXCEPTION 'activation bearer is issued once by exact worker' USING ERRCODE='23514';
   END IF;
 END IF;
 IF NEW.used_at IS DISTINCT FROM OLD.used_at THEN
   IF NEW.used_at IS NULL OR NEW.activated_user_id IS NULL
      OR OLD.revoked_at IS NOT NULL OR OLD.expires_at<=statement_timestamp()
      OR OLD.delivery_status NOT IN ('SENDING','SENT','UNKNOWN')
      OR NOT EXISTS (SELECT 1 FROM public.parents_guardianstudentrelation r
        WHERE r.user_id=NEW.activated_user_id AND r.student_id=NEW.student_id
          AND r.school_id=NEW.school_id AND r.status='ACTIVE') THEN
     RAISE EXCEPTION 'activation consumption requires exact relation' USING ERRCODE='23514';
   END IF;
 ELSIF NEW.activated_user_id IS DISTINCT FROM OLD.activated_user_id THEN
   RAISE EXCEPTION 'activation account binding requires consumption' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER parent_activation_email_guard BEFORE INSERT OR UPDATE
ON public.parents_guardianactivation FOR EACH ROW
EXECUTE FUNCTION public.xmansx_parent_activation_email_guard();
"""


def forward(apps, schema_editor):
    schema_editor.execute(original_email_guard().replace(
        " IF action = 'VERIFY' THEN", ACTIVATION_PROOF + " IF action = 'VERIFY' THEN", 1,
    ))
    schema_editor.execute(ACTIVATION_GUARD)


def backward(apps, schema_editor):
    # A restricted migration role must not mistake invisible rows for an empty DB.
    schema_editor.execute(r"""
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user AND (rolsuper OR rolbypassrls))
    OR EXISTS (SELECT 1 FROM public.parents_guardianactivation WHERE delivery_channel='EMAIL') THEN
   RAISE EXCEPTION 'unsafe guard rollback blocked: email activation data or restricted role'
     USING ERRCODE='23514';
 END IF;
END $$;
DROP TRIGGER parent_activation_email_guard ON public.parents_guardianactivation;
DROP FUNCTION public.xmansx_parent_activation_email_guard();
""")
    schema_editor.execute(original_email_guard())


class Migration(migrations.Migration):
    dependencies = [
        ("parents", "0008_retained_recovery_credential_mobile_guard"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(
            model_name="guardianactivation", name="delivery_channel",
            field=models.CharField(default="SMS", db_default="SMS", max_length=10),
        ),
        migrations.AddField(
            model_name="guardianactivation", name="email_hash",
            field=models.CharField(blank=True, default="", db_default="", max_length=64),
        ),
        migrations.AddField(
            model_name="guardianactivation", name="delivery_key",
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="guardianactivation", name="activated_user",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunSQL(
            "UPDATE parents_guardianactivation SET delivery_channel='MANUAL' "
            "WHERE delivery_status='MANUAL'",
            migrations.RunSQL.noop,
        ),
        migrations.RunPython(forward, backward),
    ]
