#!/usr/bin/env bash
set -Eeuo pipefail

# Deploy an immutable pair of images on a Linux host. The caller supplies the
# exact image coordinates produced by release.yml and keeps secrets in .env.
: "${APP_DIR:?APP_DIR must point to the checked-out deployment directory}"
: "${BACKEND_IMAGE:?BACKEND_IMAGE must include an immutable SHA tag}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE must include an immutable SHA tag}"

immutable_image='^.+:([0-9a-f]{40})$'
if [[ ! "$BACKEND_IMAGE" =~ $immutable_image || ! "$FRONTEND_IMAGE" =~ $immutable_image ]]; then
  echo "Both image coordinates must end with a full 40-character Git SHA tag." >&2
  exit 2
fi
backend_sha="${BACKEND_IMAGE##*:}"
frontend_sha="${FRONTEND_IMAGE##*:}"
if [[ "$backend_sha" != "$frontend_sha" ]]; then
  echo "Backend and frontend images must come from the same Git SHA." >&2
  exit 2
fi

ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-http://127.0.0.1:5173/api/v1/health/}"
READINESS_URL="${READINESS_URL:-http://127.0.0.1:5173/api/v1/health/ready/}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-xmansx}"
SENTRY_RELEASE="${SENTRY_RELEASE:-$backend_sha}"

if [[ ! -r "$ENV_FILE" ]]; then
  echo "Production environment file is missing or unreadable: $ENV_FILE" >&2
  exit 2
fi

cd "$APP_DIR"
compose=(
  docker compose
  --project-name "$COMPOSE_PROJECT_NAME"
  --env-file "$ENV_FILE"
  -f docker-compose.yml
  -f docker-compose.production.yml
)

export BACKEND_IMAGE FRONTEND_IMAGE SENTRY_RELEASE

# Validate interpolation before touching running services.
"${compose[@]}" config --quiet

# A release against an existing installation must leave a checksum-verified,
# remote backup before schema changes. First installation has no backend yet.
if "${compose[@]}" ps --status running --services | grep -qx backend; then
  "${compose[@]}" exec -T backend python manage.py create_database_backup
fi

"${compose[@]}" pull backend worker beat frontend
"${compose[@]}" run --rm backend python manage.py migrate --noinput
"${compose[@]}" run --rm backend python manage.py check --deploy
"${compose[@]}" up -d --no-build --remove-orphans

for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error "$HEALTHCHECK_URL" >/dev/null \
    && curl --fail --silent --show-error "$READINESS_URL" >/dev/null; then
    printf 'Release healthy: backend=%s frontend=%s\n' "$BACKEND_IMAGE" "$FRONTEND_IMAGE"
    "${compose[@]}" ps
    exit 0
  fi
  sleep 2
done

echo "Release failed health/readiness verification; traffic must not be promoted." >&2
"${compose[@]}" ps >&2
exit 1
