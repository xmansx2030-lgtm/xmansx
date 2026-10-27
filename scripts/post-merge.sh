#!/usr/bin/env bash
# Reconcile development dependencies and schema after an isolated task is merged.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Installing frontend dependencies from the lockfile..."
npm ci --prefix frontend --no-audit --no-fund

# Replit's Python user site is shared by the managed workflows; no virtualenv.
PYTHON_SITE="$(python -c 'import site; print(site.getusersitepackages())')"
echo "Installing backend dependencies..."
uv pip install --python "$(command -v python)" --target "$PYTHON_SITE" \
  "$ROOT/backend[dev,test]"

echo "Checking Django and applying development database migrations..."
bash scripts/replit-backend.sh python manage.py check
bash scripts/replit-backend.sh python manage.py migrate --noinput

echo "Post-merge development setup complete."
