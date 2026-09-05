import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User
from tests.conftest import PASSWORD


@pytest.mark.django_db
def test_bootstrap_platform_admin_creates_once_without_resetting_password(monkeypatch):
    monkeypatch.setenv("INITIAL_ADMIN_MOBILE", "0550000199")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("INITIAL_ADMIN_NAME", "مشرف المنصة")

    call_command("bootstrap_platform_admin")
    user = User.objects.get(mobile="+966550000199")
    assert user.is_staff and user.is_superuser
    assert user.first_name == "مشرف المنصة"
    assert user.check_password(PASSWORD)

    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "Different-Str0ng-Pass-2026")
    call_command("bootstrap_platform_admin")
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


@pytest.mark.django_db
def test_bootstrap_platform_admin_refuses_to_elevate_existing_user(monkeypatch, make_user):
    make_user("0550000198")
    monkeypatch.setenv("INITIAL_ADMIN_MOBILE", "0550000198")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", PASSWORD)

    with pytest.raises(CommandError, match="non-admin"):
        call_command("bootstrap_platform_admin")


@pytest.mark.django_db
def test_bootstrap_platform_admin_requires_deployment_values(monkeypatch):
    monkeypatch.delenv("INITIAL_ADMIN_MOBILE", raising=False)
    monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)

    with pytest.raises(CommandError, match="required"):
        call_command("bootstrap_platform_admin")
