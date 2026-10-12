#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

cd /opt/mowadhabah
compose=(docker compose --project-name mowadhabah --env-file .env -f compose.yaml)
"${compose[@]}" config --quiet
if "${compose[@]}" ps --status running --services | grep -q '^backend$'; then
    echo 'A replacement application is already running; refusing to repeat restore.' >&2
    exit 2
fi

"${compose[@]}" pull postgres redis frontend
"${compose[@]}" up -d postgres redis storage-init
for attempt in $(seq 1 30); do
    if "${compose[@]}" exec -T postgres pg_isready -U postgres -d mowadhabah >/dev/null; then
        break
    fi
    sleep 1
done

backend_image=$(sed -n 's/^BACKEND_IMAGE=//p' .env | tr -d '\r')
docker run --rm --network mowadhabah_backend \
    --env-file application.env --env-file database-admin.env \
    -v /opt/mowadhabah/bootstrap_database.py:/tmp/bootstrap_database.py:ro \
    --entrypoint python "$backend_image" /tmp/bootstrap_database.py

python3 - <<'PY'
import hashlib, json
from pathlib import Path
root = Path('/opt/mowadhabah/restore')
dumps = list(root.glob('*.dump'))
assert len(dumps) == 1, 'Require exactly one original source dump'
dump = dumps[0]
manifest = json.loads(dump.with_suffix('.json').read_text())
assert manifest['filename'] == dump.name
assert hashlib.file_digest(dump.open('rb'), 'sha256').hexdigest() == manifest['sha256']
assert dump.stat().st_size == manifest['size_bytes']
print('Original source dump and manifest checksum verified on replacement host')
PY

"${compose[@]}" exec -T postgres sh -ec '
    export PGUSER="$POSTGRES_APP_USER"
    export PGPASSWORD="$POSTGRES_APP_PASSWORD"
    export PGOPTIONS="-c app.rls_bypass=on"
    set -- /restore/*.dump
    test "$#" -eq 1
    exec pg_restore --exit-on-error --no-owner --no-privileges --dbname "$POSTGRES_DB" "$1"
'

bash /opt/mowadhabah/verify_stage.sh
