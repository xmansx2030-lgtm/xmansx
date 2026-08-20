"""Focused Phase 17 production and response hardening gates."""

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, override_settings

from documents.storage import generated_document_path
from excuses.models import excuse_attachment_path

PRODUCTION_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DJANGO_SECRET_KEY": (
        "phase17-test-secret-with-more-than-fifty-characters-and-real-variety-9274"
    ),
    "DJANGO_ALLOWED_HOSTS": "app.example.test",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.example.test",
    "POSTGRES_DB": "phase17",
    "POSTGRES_USER": "phase17",
    "POSTGRES_PASSWORD": "phase17-database-password",
    "POSTGRES_HOST": "postgres",
    "POSTGRES_PORT": "5432",
    "REDIS_URL": "redis://redis:6379/0",
    "FIELD_ENCRYPTION_KEYS": "ehl1c-0LD6bf60FHqC3_5VdHF1gcn6tZYpqUg_knyJ0=",
    "NATIONAL_ID_HMAC_KEY": "phase17-hmac-key-with-at-least-32-characters",
}


def _load_production_settings(overrides=None, *, remove=()):
    env = {**os.environ, **PRODUCTION_ENV, **(overrides or {})}
    for name in remove:
        env.pop(name, None)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from django.conf import settings; "
                "print(settings.DEBUG, settings.SESSION_COOKIE_AGE, "
                "settings.SESSION_COOKIE_SECURE, settings.CSRF_COOKIE_SECURE)"
            ),
        ],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_production_settings_are_secure_and_load_with_explicit_environment():
    result = _load_production_settings()
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False 43200 True True"


@pytest.mark.parametrize(
    ("overrides", "remove", "expected"),
    [
        ({}, ("DJANGO_SECRET_KEY",), "Missing required environment variable"),
        ({"DJANGO_ALLOWED_HOSTS": "*"}, (), "cannot contain '*'"),
        (
            {"DJANGO_CSRF_TRUSTED_ORIGINS": "http://untrusted.example.test"},
            (),
            "explicit HTTPS origins",
        ),
        (
            {"FIELD_ENCRYPTION_KEYS": "g8_LpA8xmZcbg6EMSduJi5tKU9zdBr0HncpN9zAcFNo="},
            (),
            "development key",
        ),
    ],
)
def test_production_settings_fail_fast_without_exposing_values(overrides, remove, expected):
    result = _load_production_settings(overrides, remove=remove)
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert expected in output
    for secret_name in ("DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "NATIONAL_ID_HMAC_KEY"):
        assert PRODUCTION_ENV[secret_name] not in output


def test_api_responses_disable_persistent_caching_and_set_security_headers():
    response = Client().get("/api/v1/health/")

    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store, max-age=0"
    assert response["Pragma"] == "no-cache"
    assert response["Expires"] == "0"
    assert response["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response["Permissions-Policy"] == (
        "camera=(self), microphone=(), geolocation=(), payment=(), usb=()"
    )


@pytest.mark.parametrize("filename", ["../../secret.pdf", r"..\..\secret.jpg"])
def test_private_storage_keys_ignore_user_controlled_paths(filename):
    instance = SimpleNamespace(school_id=42)
    excuse_key = excuse_attachment_path(instance, filename)
    document_key = generated_document_path(instance, filename)

    assert excuse_key.startswith("excuse_attachments/school_42/")
    assert document_key.startswith("school_42/")
    assert "secret" not in excuse_key
    assert ".." not in excuse_key
    assert ".." not in document_key


@override_settings(
    DEBUG=False,
    SECURE_SSL_REDIRECT=True,
    ALLOWED_HOSTS=["app.example.test"],
)
@pytest.mark.django_db
def test_dev_seed_cannot_be_enabled_in_a_real_production_configuration():
    with pytest.raises(CommandError, match="DEBUG=True"):
        call_command(
            "seed_dev",
            password="not-used-because-guard-runs-first",
            allow_production_like=True,
        )


@override_settings(
    DEBUG=False,
    SECURE_SSL_REDIRECT=True,
    ALLOWED_HOSTS=["app.example.test"],
)
def test_attendance_seed_cannot_be_enabled_in_real_production():
    with pytest.raises(CommandError, match="التطوير فقط"):
        call_command("seed_attendance_sessions", allow_production_like=True)
