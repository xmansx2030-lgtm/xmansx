# syntax=docker/dockerfile:1

# ---------- Base ----------
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# ---------- Dependencies ----------
FROM base AS deps
COPY pyproject.toml ./
# نثبت الاعتماديات فقط (المشروع ليس مكتبة) — test extras للتطوير فقط
RUN pip install --prefix=/install ".[test]" && rm -rf /app/build /app/*.egg-info

# ---------- Development ----------
FROM base AS dev
COPY --from=deps /install /usr/local
COPY . .
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---------- Production ----------
FROM base AS prod
# لا نشغل الإنتاج كـ root
RUN addgroup --system app && adduser --system --ingroup app app
COPY --from=deps /install /usr/local
# ننسخ الكود فقط — لا .env ولا git history ولا artifacts (انظر .dockerignore)
COPY --chown=app:app . .
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
