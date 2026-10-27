#!/usr/bin/env bash
set -euo pipefail

# Replit's provisioned development PostgreSQL exposes PG* variables.
# The existing Django settings expect POSTGRES_* variables instead.
export POSTGRES_DB="${PGDATABASE:?Replit PostgreSQL is not configured}"
export POSTGRES_USER="${PGUSER:?Replit PostgreSQL is not configured}"
export POSTGRES_PASSWORD="${PGPASSWORD:?Replit PostgreSQL is not configured}"
export POSTGRES_HOST="${PGHOST:?Replit PostgreSQL is not configured}"
export POSTGRES_PORT="${PGPORT:?Replit PostgreSQL is not configured}"
export DJANGO_SETTINGS_MODULE=config.settings.local
export REDIS_URL=redis://127.0.0.1:6379/0
export CACHE_REDIS_URL=redis://127.0.0.1:6379/0
export SECURITY_REDIS_URL=redis://127.0.0.1:6379/1
export CELERY_BROKER_URL=redis://127.0.0.1:6379/2
export CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/3

cd backend
exec "$@"