# syntax=docker/dockerfile:1

# ---------- Base ----------
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# مكتبات نظام توليد PDF (WeasyPrint): تخطيط نصي عربي وتشكيل عبر Pango/HarfBuzz/FriBidi،
# ورسم عبر Cairo. الخطوط من حزمة Noto (رخصة OFL) — لا ملفات خطوط داخل المستودع.
FROM base AS runtime-libs
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libfribidi0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        fonts-noto-core \
        postgresql-common \
    && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/*

# ---------- Dependencies ----------
FROM base AS deps
COPY pyproject.toml ./
# نثبت الاعتماديات فقط (المشروع ليس مكتبة) — test extras للتطوير فقط
RUN pip install --prefix=/install ".[test]" && rm -rf /app/build /app/*.egg-info

# ---------- Development ----------
FROM runtime-libs AS dev
COPY --from=deps /install /usr/local
COPY . .
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---------- Production ----------
FROM runtime-libs AS prod
# لا نشغل الإنتاج كـ root
RUN addgroup --system app && adduser --system --ingroup app app
ENV XDG_CACHE_HOME=/tmp/.cache
COPY --from=deps /install /usr/local
# ننسخ الكود فقط — لا .env ولا git history ولا artifacts (انظر .dockerignore)
COPY --chown=app:app . .
RUN mkdir -p /app/mediafiles /app/privatefiles/documents /app/staticfiles /app/storage \
        /tmp/.cache/fontconfig \
    && chown -R app:app /app/mediafiles /app/privatefiles /app/staticfiles /app/storage \
        /tmp/.cache
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--config", "config/gunicorn.conf.py"]
