"""اختبارات المستخدم المخصص: التفرد، Argon2، createsuperuser، المعطل."""

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import override_settings

from accounts.models import User
from tests.conftest import PASSWORD

ARGON2_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]


@pytest.mark.django_db
def test_user_mobile_is_normalized_on_create(make_user):
    user = make_user("0550000100")
    assert user.mobile == "+966550000100"


@pytest.mark.django_db
def test_mobile_unique_globally(make_user):
    make_user("0550000101")
    with pytest.raises(Exception) as excinfo:  # ValidationError من full_clean أو IntegrityError
        with transaction.atomic():
            make_user("+966550000101")  # نفس الرقم بصيغة أخرى
    assert excinfo.type is not None


@pytest.mark.django_db
def test_mobile_unique_at_database_level(make_user):
    """القيد في قاعدة البيانات نفسها وليس Validation فقط."""
    make_user("0550000102")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.bulk_create([User(mobile="+966550000102")])  # يتجاوز full_clean


@pytest.mark.django_db
@override_settings(PASSWORD_HASHERS=ARGON2_HASHERS)
def test_password_hashed_with_argon2id():
    user = User.objects.create_user(mobile="0550000103", password=PASSWORD)
    assert user.password.startswith("argon2$argon2id$")
    assert PASSWORD not in user.password
    assert user.check_password(PASSWORD)


@pytest.mark.django_db
def test_password_never_stored_raw(make_user):
    user = make_user("0550000104")
    assert PASSWORD not in user.password


@pytest.mark.django_db
def test_createsuperuser_with_mobile(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", PASSWORD)
    call_command("createsuperuser", "--noinput", "--mobile", "0550000105")
    user = User.objects.get(mobile="+966550000105")
    assert user.is_superuser and user.is_staff
    assert user.is_platform_admin


@pytest.mark.django_db
def test_inactive_user_cannot_login(make_user, login_client):
    user = make_user("0550000106")
    user.is_active = False
    user.save(update_fields=["is_active"])
    _, response = login_client("0550000106")
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"
