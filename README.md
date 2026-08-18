# منصة المواظبة والمتابعة الطلابية

منصة SaaS متعددة المدارس لإدارة حضور الطلاب وغيابهم وتأخرهم والأعذار والإنذارات والإجراءات والإحالات والمتابعة الإرشادية والتقارير والاشتراكات.

**الحالة:** المرحلة 1 (Foundation) — أساس تقني فقط، لا Features أعمال بعد. انظر [PHASE_1_REPORT.md](PHASE_1_REPORT.md).

## المتطلبات (Requirements)

- Python 3.13+
- Node.js 24+ (LTS)
- Docker + Docker Compose (لـ PostgreSQL 18 وRedis والتشغيل الكامل)
- Git

## بنية المشروع

```text
xmansx/
├── backend/          # Django 5.2 + DRF (config/, common/, tests/)
├── frontend/         # React 19 + TypeScript + Vite + Tailwind 4 (Feature-Based)
├── docs/             # وثائق المعمارية والتصميم (المرحلة 0)
├── infra/            # ملفات بنية تحتية (لاحقًا)
├── scripts/          # سكربتات مساعدة (لاحقًا)
├── .github/          # GitHub Actions CI
├── docker-compose.yml
└── .env.example
```

## الإعداد المحلي (Local setup)

```bash
git clone <repo>
cd xmansx
cp .env.example .env        # عدل القيم إن لزم — لا تضع .env في Git أبدًا
```

### التشغيل الكامل عبر Docker (الأسهل)

```bash
docker compose up
# Backend:  http://localhost:8000/api/v1/health/
# Frontend: http://localhost:5173
```

يشغل: postgres + redis + backend + frontend + worker (Celery) + beat (Celery Beat).

### تشغيل Backend على الجهاز مباشرة

```bash
docker compose up -d postgres redis     # الخدمات فقط
cd backend
python -m venv .venv
.venv\Scripts\activate                  # Windows | source .venv/bin/activate على Linux/Mac
pip install -e ".[dev,test]"
python manage.py migrate
python manage.py runserver
```

### تشغيل Frontend على الجهاز مباشرة

```bash
cd frontend
npm ci
npm run dev                             # http://localhost:5173 (يعمل proxy لـ /api → :8000)
```

## متغيرات البيئة (Environment variables)

انظر [.env.example](.env.example) — أهمها:

| المتغير | الوصف |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.local` / `test` / `production` |
| `DJANGO_SECRET_KEY` | إلزامي في الإنتاج (يفشل التشغيل بدونه) |
| `DJANGO_ALLOWED_HOSTS` | إلزامي في الإنتاج، مفصول بفواصل |
| `POSTGRES_*` | اتصال قاعدة البيانات (إلزامية في الإنتاج) |
| `REDIS_URL` | إلزامي في الإنتاج |

## أوامر Backend

```bash
cd backend
pytest                                       # الاختبارات (تتطلب postgres وredis)
ruff check .                                 # lint
python manage.py check                       # Django system checks
python manage.py makemigrations --check      # لا migrations ناقصة
python manage.py migrate                     # تطبيق migrations
celery -A config worker --loglevel=info      # worker (داخل Docker على Windows)
celery -A config beat --loglevel=info        # beat
```

## أوامر Frontend

```bash
cd frontend
npm run dev          # تشغيل التطوير
npm run test         # Vitest
npm run typecheck    # TypeScript strict
npm run lint         # ESLint
npm run build        # بناء الإنتاج
npm run e2e          # Playwright smoke (يتطلب backend على :8000)
```

## الاختبارات

- **Backend:** pytest + pytest-django على PostgreSQL حقيقي (health, readiness, بنية الأخطاء, request-id, celery eager).
- **Frontend:** Vitest + React Testing Library (render, RTL, 404, طبقة API).
- **E2E:** Playwright smoke — فتح الواجهة والتحقق من الوصول الفعلي للـ backend.

## CI

GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)): backend (ruff + checks + migrations + pytest مع postgres/redis) + frontend (lint + typecheck + tests + build) + فحص أسرار (gitleaks).

## الوثائق

| الوثيقة | المحتوى |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | المعمارية والوحدات والحدود |
| [docs/adr/](docs/adr/) | سجلات القرارات المعمارية |
| [docs/ERD.md](docs/ERD.md) | الكيانات والعلاقات والقيود |
| [docs/PERMISSIONS.md](docs/PERMISSIONS.md) | مصفوفة الصلاحيات |
| [docs/SECURITY.md](docs/SECURITY.md) | النموذج الأمني |
| [docs/PHASE_PLAN.md](docs/PHASE_PLAN.md) | خطة المراحل 0–20 |
