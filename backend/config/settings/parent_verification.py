"""Isolated synthetic HTTP verification with real restricted-role RLS context."""

import os

from django.core.exceptions import ImproperlyConfigured

from .local import *

_expected_verification_environment = {
    "PARENT_VERIFICATION_LOCAL_ONLY": "1",
    "POSTGRES_DB": "parent_verification",
    "POSTGRES_USER": "parent_verify_app",
    "POSTGRES_HOST": "postgres",
}
if any(os.environ.get(key) != value for key, value in _expected_verification_environment.items()):
    raise ImproperlyConfigured("Parent verification settings require the isolated local stack")

DATABASE_RLS_ENFORCED = True
