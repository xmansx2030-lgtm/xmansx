#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
cd /opt/mowadhabah
compose=(docker compose --project-name mowadhabah --env-file .env -f compose.yaml)

"${compose[@]}" run --rm --no-deps \
    -v /opt/mowadhabah/data_inventory.py:/tmp/data_inventory.py:ro \
    backend python /tmp/data_inventory.py > /opt/mowadhabah/restore-inventory.json
"${compose[@]}" run --rm --no-deps backend python manage.py migrate --check
"${compose[@]}" run --rm --no-deps backend python manage.py check --deploy
"${compose[@]}" up -d backend frontend
for attempt in $(seq 1 30); do
    if curl -fsS -H 'Host: mowadhabah.com' http://127.0.0.1:9085/api/v1/health/ >/dev/null \
        && curl -fsS -H 'Host: mowadhabah.com' http://127.0.0.1:9085/api/v1/readiness/ >/dev/null; then
        echo 'Replacement web, PostgreSQL and Redis are ready; public DNS is unchanged.'
        "${compose[@]}" ps
        exit 0
    fi
    sleep 2
done
echo 'Replacement readiness failed; public DNS must not be promoted.' >&2
exit 1
