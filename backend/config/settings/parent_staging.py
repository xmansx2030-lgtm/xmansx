"""Loopback-only synthetic acceptance using the real production security profile.

This profile cannot select a remote database, SMS provider or public origin.
The Compose services using it have an internal network with no external route.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .production import *

_expected = {
    "PARENT_STAGING_LOCAL_ONLY": "1",
    "POSTGRES_DB": "parent_verification",
    "POSTGRES_USER": "parent_verify_app",
    "POSTGRES_HOST": "postgres",
    "PARENT_PORTAL_BASE_URL": "https://localhost:8445",
}
if any(os.environ.get(key) != value for key, value in _expected.items()):
    raise ImproperlyConfigured("Synthetic staging requires its isolated loopback stack")
if (
    ALLOWED_HOSTS != ["localhost"]
    or CSRF_TRUSTED_ORIGINS != ["https://localhost:8445"]
    or CORS_ALLOWED_ORIGINS
    or DJANGO_ADMIN_ENABLED
    or SELF_REGISTRATION_ENABLED
    or not SECURE_SSL_REDIRECT
    or SENTRY_DSN
    or R2_ENABLED
    or R2_BACKUP_ENABLED
    or BACKUP_REMOTE_ENABLED
    or os.environ.get("BACKUP_SCHEDULE_ENABLED") != "false"
    or MINISTRY_CALENDAR_ENABLED
):
    raise ImproperlyConfigured("Synthetic staging refuses external services or public access")

# Do not turn local certificate acceptance into a browser-wide persistent HSTS
# policy. TLS redirect, secure cookies and all other production protections stay.
SECURE_HSTS_SECONDS = 0

# Private volumes remain restrictive after new uploads, not just initialization.
FILE_UPLOAD_PERMISSIONS = 0o600
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o700

# Local synthetic delivery never connects to Resend or another mail transport.
PARENT_STAGING_LOCAL_ONLY = True
if RESEND_API_KEY or PARENT_RECOVERY_EMAIL_ADAPTER != "synthetic-file":
    raise ImproperlyConfigured("Synthetic staging requires its private fake recovery mailbox")
if (
    PARENT_FAMILY_INVITATION_SMS_ENABLED
    and PARENT_FAMILY_INVITATION_SMS_ADAPTER != "synthetic-file"
):
    raise ImproperlyConfigured("Synthetic staging refuses external invitation SMS")
