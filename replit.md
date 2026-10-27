# Running the school platform on Replit

This workspace runs the imported Django/React project in **development mode**. The
original Docker Compose configuration remains for local/Docker use. This is **not**
a production deployment: Django's local settings use development-only encryption
and signing defaults. Do not enter real school or student data here or publish this
configuration as a production service.

## Services and startup

The Replit **Run** button starts the `Project` workflow, which starts Redis, the
React/Vite preview (`Start application`), the Django API (`Backend API`), the
Celery worker, and Celery beat. The preview is served on port 5000. Vite proxies
`/api` to Django on port 8000 so the browser uses one origin. Redis binds to
127.0.0.1:6379 with an append-only file under `.cache/redis/`. Backend processes
use `scripts/replit-backend.sh` to map the provisioned Replit **development**
PostgreSQL `PG*` variables to the project's existing `POSTGRES_*` settings.
Only this workspace's Replit HTTPS preview origin is added to Django's local
CSRF trusted origins; production settings are unchanged.
The development database starts empty; no data from Docker or another server
was imported. Do not replace a real database with it without an explicit migration
plan.

If starting from a clean workspace, install Python 3.13, Node.js 24, Redis and
the project dependencies (Python project in `backend/pyproject.toml`, frontend
using `cd frontend && npm ci`). Then start Redis and run migrations once:

```bash
bash scripts/replit-backend.sh python manage.py migrate --noinput
```

The backend wrapper requires Replit's provisioned PostgreSQL variables. It does
not use or store credentials in the repository. The development settings use
existing local-only keys; for a production deployment, obtain real secrets and
service configuration from the owner and follow the production checklist rather
than using this Run workflow.

## Checks

- Preview: open the web view on port 5000.
- Liveness: `/api/v1/health/` should return `{"status":"ok"}`.
- Readiness: `/api/v1/readiness/` should report `database` and `redis` as `ok`.
- To run Django commands: `bash scripts/replit-backend.sh python manage.py check`.

New databases have no accounts or school data. Sign-in requires an account to be
created through the existing registration/admin flows.