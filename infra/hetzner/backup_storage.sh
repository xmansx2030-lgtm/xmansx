#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
cd /opt/mowadhabah
exec 9>/run/lock/mowadhabah-files-backup.lock
flock -n 9
docker compose exec -T backend python - < /opt/mowadhabah/backup_storage.py
