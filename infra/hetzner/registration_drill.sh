#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
cd /opt/mowadhabah
qa_database=mowadhabah_registration_drill_20261012
existing=$(docker exec mowadhabah-postgres-1 psql -U postgres -qAt -c "SELECT 1 FROM pg_database WHERE datname='$qa_database'")
test -z "$existing" || { echo 'QA database already exists; refusing to overwrite it.' >&2; exit 2; }
docker exec mowadhabah-postgres-1 createdb -U postgres --owner=mowadhabah_app "$qa_database"
docker exec mowadhabah-postgres-1 sh -ec '
    export PGUSER="$POSTGRES_APP_USER" PGPASSWORD="$POSTGRES_APP_PASSWORD"
    set -- /restore/*.dump
    test "$#" -eq 1
    pg_restore --exit-on-error --no-owner --no-privileges --dbname mowadhabah_registration_drill_20261012 "$1"
'
backend_image=$(sed -n 's/^BACKEND_IMAGE=//p' .env | tr -d '\r')
docker run --rm --network mowadhabah_backend --env-file application.env \
    -e POSTGRES_DB="$qa_database" \
    -e REDIS_URL=redis://redis:6379/10 -e CACHE_REDIS_URL=redis://redis:6379/10 \
    -e SECURITY_REDIS_URL=redis://redis:6379/11 -e CELERY_BROKER_URL=redis://redis:6379/12 \
    -e CELERY_RESULT_BACKEND=redis://redis:6379/13 \
    -e SUBSCRIPTION_EMAIL_ENABLED=false -e PARENT_RECOVERY_EMAIL_ENABLED=false \
    -e SCHOOL_ACCOUNT_EMAIL_RECOVERY_ENABLED=false -e PARENT_FAMILY_INVITATION_SMS_ENABLED=false \
    -v /opt/mowadhabah/registration_drill.py:/tmp/registration_drill.py:ro \
    --entrypoint python "$backend_image" /tmp/registration_drill.py
