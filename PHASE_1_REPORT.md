# PHASE 1 REPORT — Foundation

**التاريخ:** 2026-08-18

## Status

`COMPLETE` — كل معايير القبول (البند 33) تحققت بتشغيل فعلي موثق أدناه، عدا بندين بيئيين مذكورين صراحة كـ NOT RUN مع السبب.

## Implemented

- Git repository مهيأ + `.gitignore` شامل (Python/Django/Node/Vite/IDEs/env/secrets/build/test/coverage/data).
- Backend: Django 5.2.17 LTS + DRF 3.16.1 على Python 3.13.14، بإعدادات مقسمة (`base/local/test/production`) وقراءة بيئة صريحة تفشل بوضوح عند النقص.
- `common/`: Request-ID middleware، Structured JSON logging، بنية أخطاء موحدة `{code, message, details}` برسائل عربية، health/readiness، مهمة `foundation_ping` تقنية معلّمة بوضوح أنها Foundation فقط.
- Celery 5.6.3 + Beat: بنية تشغيل فقط، تعمل داخل Compose.
- Frontend: React 19.2.8 + TypeScript 6.0.3 (strict) + Vite 8.2.1 + Tailwind 4.3.3 + TanStack Query 5.101 ببنية Feature-Based، RTL/عربي من الجذر، App shell + 404 + Error + Loading + Button/TextField أساسية، طبقة `api/client.ts` مركزية (credentials, أخطاء موحدة, timeout/cancellation, request-id).
- Docker: Dockerfiles multi-stage (الإنتاج غير root، بلا .env/.git)، Compose بست خدمات مع healthchecks.
- CI: GitHub Actions (backend + frontend + gitleaks). اختبارات فعلية: 12 backend (على PostgreSQL 18 وRedis حقيقيين) + 8 frontend + 1 E2E Playwright.

## Project structure

```text
xmansx/
├── backend/            # manage.py, pyproject.toml, config/{settings,celery,env,urls,wsgi,asgi}, common/, tests/
├── frontend/           # src/{app,routes,features,components,api,hooks,stores,types,utils,styles}, e2e/
├── docs/               # وثائق المرحلة 0 (بلا تغيير)
├── infra/  scripts/    # placeholders
├── .github/workflows/ci.yml
├── docker-compose.yml  # postgres, redis, backend, frontend, worker, beat
├── .env.example  .gitignore  README.md
```

لم تُنشأ أي وحدة أعمال (accounts/schools/attendance/...) — التزامًا بالبند 32.

## Dependencies

- Backend (`backend/pyproject.toml`): Django 5.2.17، DRF 3.16.1، psycopg 3.3.4، celery 5.6.3، redis 6.4.0، django-cors-headers 4.9.0، django-csp 4.0، gunicorn 23.0.0. اختيارية: dev=[ruff 0.16.3]، test=[pytest 8.4.2، pytest-django 4.14.0].
- Frontend (`frontend/package.json` + lockfile): react 19.2.8، react-router-dom 7.18.2، @tanstack/react-query 5.101.4؛ dev: vite 8.2.1، typescript 6.0.3، tailwindcss 4.3.3، vitest 4.1.10، @testing-library/react 16.3.2، eslint 10.8.1 + typescript-eslint 8.67، @playwright/test 1.62.1، @types/node.

## Configuration

- `config/env.py`: `env_str/bool/int/list` — النقص بلا default = `ImproperlyConfigured` فوري.
- `production.py` يفرض إلزاميًا: `DJANGO_SECRET_KEY` (ويرفض قيم django-insecure)، `DJANGO_ALLOWED_HOSTS`، `POSTGRES_*`، `REDIS_URL` — تم التحقق بالتشغيل الفعلي (انظر Results).
- `.env.example` بقيم وهمية فقط؛ لا أسرار في Git.
- ملاحظة بيئة محلية: منفذ PostgreSQL على الجهاز **5433** (حاوية → 5432 داخليًا) لوجود عملية postgres محلية غريبة تحتل 5432 على جهاز التطوير — لم نوقفها لأنها ليست تابعة للمشروع.

## Docker

Compose بست خدمات، كلها اشتغلت فعليًا: postgres:18-alpine (healthy)، redis:8.0-alpine (healthy)، backend (dev target)، frontend (Vite + proxy `/api` → backend:8000)، worker، beat. الإنتاج: backend عبر gunicorn بمستخدم غير root، وfrontend static عبر nginx مع proxy `/api` (تقليل CORS لنفس الـ Origin).

## API foundation

- `/api/v1/health/` → `{"status": "ok"}` (بلا فحوص خارجية، بلا تسريب).
- `/api/v1/readiness/` → فحص PostgreSQL + Redis بمهلة ثانيتين → `{"status","checks"}` مع 503 عند الفشل، بلا تفاصيل داخلية.
- DRF: JSON فقط، `IsAuthenticated` افتراضيًا (health تصرح AllowAny)، exception handler موحد، `X-Request-ID` في كل استجابة (تمرير الوارد الآمن فقط — regex ضد log injection).

## Frontend foundation

RTL/عربية من `index.html` (`lang="ar" dir="rtl"`)، App shell + Home مؤقتة تعرض حالة الاتصال بالخادم عبر TanStack Query، صفحات 404 وError، طبقة API مركزية تمنع fetch العشوائي، TS strict كامل (`noUncheckedIndexedAccess` وغيرها)، `@typescript-eslint/no-explicit-any: error`.

## Security baseline

- Production: `SECURE_SSL_REDIRECT`، HSTS (30 يومًا بداية)، Secure/HttpOnly/SameSite cookies، CSRF، nosniff، Referrer-Policy، `X-Frame-Options: DENY`، CSP صارمة عبر django-csp (`default-src 'self'`).
- CORS: مغلق افتراضيًا؛ local يسمح لـ Vite فقط؛ لا `CORS_ALLOW_ALL_ORIGINS` في أي بيئة.
- Docker إنتاج: non-root، بلا secrets/git داخل الصورة.
- CI يتضمن gitleaks.

## Logging

JSON logs بحقول: timestamp, level, logger, message, request_id + حقول الطلب (method, path, status_code, duration_ms). لا headers ولا cookies ولا passwords. `user_id/school_id` تضاف في المرحلة 2 كما هو مخطط.

## Testing

- Backend (pytest + pytest-django على PostgreSQL 18 + Redis حقيقيين): health، عدم تسريب، readiness ناجح، readiness مع Redis ساقط → 503، بنية أخطاء 404/405 الموحدة، عدم وجود stack traces، توليد/تمرير/رفض X-Request-ID، أمان إعدادات test، تنفيذ مهمة Celery eager.
- Frontend (Vitest + RTL): render الهيكل، RTL+lang، حالة الاتصال، صفحة 404، طبقة API (نجاح/خطأ موحد/فشل شبكة/credentials).
- E2E (Playwright/Chromium): فتح الواجهة → RTL+عربية → العنوان → وصول فعلي للـ backend عبر proxy الحاوية.

## CI

`.github/workflows/ci.yml`: backend (pip install, ruff, `manage.py check`, `makemigrations --check`, pytest مع postgres/redis services) + frontend (npm ci, lint, typecheck, test, build) + secrets scan (gitleaks). **لم يُشغَّل** — لا remote بعد (انظر Results).

## Commands executed / Results

| # | الأمر | النتيجة |
|---|---|---|
| 1 | `git init` | PASS — repo مهيأ |
| 2 | `pip install -e ".[dev,test]"` (venv py3.13.14) | PASS |
| 3 | `ruff check .` (backend) | **PASS** — "All checks passed!" |
| 4 | `python manage.py check` | **PASS** — 0 issues |
| 5 | `python manage.py makemigrations --check --dry-run` | **PASS** — "No changes detected" (exit 0) |
| 6 | `pytest` (backend، على postgres:18 + redis:8 عبر Docker) | **PASS — 12/12** في 3.03s |
| 7 | `python manage.py migrate` (local DB) | **PASS** — كل migrations الأساس طُبقت |
| 8 | `django.setup()` بإعدادات production بلا env | **PASS (فشل مقصود)** — `ImproperlyConfigured: Missing DJANGO_SECRET_KEY` |
| 9 | `npm run lint` | **PASS** (exit 0) |
| 10 | `npm run typecheck` (`tsc -b`) | **PASS** (exit 0) |
| 11 | `npm run test` (Vitest) | **PASS — 8/8** |
| 12 | `npm run build` (vite 8.2.1) | **PASS** — dist مبني (JS 320KB / gzip 101KB) |
| 13 | `docker compose up -d --build` | **PASS** — 6 خدمات Up |
| 14 | `GET :8000/api/v1/health/` | **PASS** — `{"status":"ok"}` + X-Request-ID |
| 15 | `GET :8000/api/v1/readiness/` | **PASS** — `{"status":"ready","checks":{"database":"ok","redis":"ok"}}` |
| 16 | `celery -A config inspect ping` (worker) | **PASS** — pong، 1 node online |
| 17 | `foundation_ping.delay().get()` عبر broker حقيقي | **PASS** — "pong" |
| 18 | logs beat | **PASS** — "beat: Starting..." |
| 19 | `GET :5173` + proxy `:5173/api/v1/health/` | **PASS** — 200 + `{"status":"ok"}` |
| 20 | `npx playwright test` (smoke) | **PASS — 1/1** |
| 21 | GitHub Actions | **NOT RUN** — لا remote مصرح به بعد؛ الملف جاهز ويعمل عند أول push |
| 22 | gitleaks محليًا | **NOT RUN** — الأداة غير مثبتة محليًا؛ تعمل ضمن CI |

## Known limitations

- صفحة Home مؤقتة (مؤشر اتصال) — تستبدل بشاشة الدخول في المرحلة 2.
- `manage.py check --deploy` سيُدرج ضمن فحوص الإنتاج عند أول بيئة إنتاج فعلية (المتغيرات الإلزامية غير متوفرة محليًا بالتصميم).
- Playwright يعمل محليًا فقط حاليًا؛ إدراجه في CI مؤجل حتى تستقر صفحات فعلية (تجنب flakiness بلا قيمة).
- منفذ postgres المحلي 5433 (توثيق في README/.env.example) بسبب تعارض بيئة الجهاز.

## Technical debt

- تثبيت أدق للإصدارات عبر lockfile للـ backend (pip freeze → ملف constraints) يُقيّم في مرحلة لاحقة؛ الحدود العليا/الدنيا مثبتة في pyproject حاليًا.
- `SECURE_HSTS_SECONDS` يبدأ بـ 30 يومًا ويُرفع بعد استقرار الإنتاج (مقصود).

## Security observations

- الافتراضي المغلق مطبق: DRF `IsAuthenticated` افتراضيًا، CORS فارغ افتراضيًا، CSP `self` فقط.
- التحقق الفعلي أن production تفشل عند نقص المتغيرات (السطر 8 أعلاه).
- X-Request-ID الوارد يمر عبر regex صارم (منع log injection) — مغطى باختبار.
- لا أسرار في الشجرة: `.env` غير موجود أصلًا، و`.gitignore` يمنعه.

## Risks

| الخطر | التخفيف |
|---|---|
| عملية postgres المحلية الغريبة على 5432 قد تسبب لبسًا لمطور جديد | موثق في README و.env.example (استخدام 5433) |
| فرق نسخ TS 6 / ESLint 10 عن قوالب شائعة | الإعدادات مضبوطة ومختبرة فعليًا في هذه المرحلة |
| CI لم يُشغّل بعد | أول push سيثبته؛ الأوامر نفسها شُغلت محليًا بنجاح |

## Files changed

88 ملفًا جديدًا (لا حذف ولا تعديل على وثائق المرحلة 0). أبرزها: `backend/` (17 ملف Python + pyproject + Dockerfile)، `frontend/` (24 ملف TS/TSX + configs + Dockerfile)، `docker-compose.yml`، `.github/workflows/ci.yml`، `.env.example`، `.gitignore`، README محدث.

## Ready for Phase 2?

**نعم.** الأساس يعمل بكامل خدماته والفحوص خضراء. المرحلة 2 (Accounts + Multi-Tenancy) يمكن أن تبدأ فور الاعتماد: User بالجوال المطبّع + Argon2، School، SchoolMembership، MembershipRole، الدخول/الخروج/اختيار وتبديل المدرسة، Middleware العزل، واختبارات العزل الصارمة.
