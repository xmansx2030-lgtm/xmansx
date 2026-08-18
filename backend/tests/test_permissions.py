"""اختبارات وحدات الصلاحيات المركزية وسياق المستأجر (بدون endpoints أعمال)."""

import pytest
from rest_framework.views import APIView

from common.errors import ApiError
from memberships.permissions import (
    ActiveSchoolRequired,
    has_any_school_role,
    has_school_role,
    require_school_role,
    school_role_required,
)


class _FakeRequest:
    def __init__(self, user=None, school=None, roles=None, error=None):
        self.user = user
        self.school = school
        self.school_roles = roles or []
        self.school_context_error = error


class _AuthedUser:
    is_authenticated = True
    must_change_password = False


def test_has_school_role_requires_active_school():
    request = _FakeRequest(user=_AuthedUser(), school=None, roles=["TEACHER"])
    assert has_school_role(request, "TEACHER") is False


def test_has_school_role_checks_current_school_roles():
    request = _FakeRequest(user=_AuthedUser(), school=object(), roles=["TEACHER"])
    assert has_school_role(request, "TEACHER") is True
    assert has_school_role(request, "SCHOOL_MANAGER") is False
    assert has_any_school_role(request, ["SCHOOL_MANAGER", "TEACHER"]) is True


def test_require_school_role_raises_active_school_required():
    request = _FakeRequest(user=_AuthedUser(), school=None)
    with pytest.raises(ApiError) as excinfo:
        require_school_role(request, "TEACHER")
    assert excinfo.value.code == "ACTIVE_SCHOOL_REQUIRED"


def test_require_school_role_raises_specific_context_error():
    request = _FakeRequest(user=_AuthedUser(), school=None, error="MEMBERSHIP_SUSPENDED")
    with pytest.raises(ApiError) as excinfo:
        require_school_role(request, "TEACHER")
    assert excinfo.value.code == "MEMBERSHIP_SUSPENDED"


def test_require_school_role_denies_missing_role():
    request = _FakeRequest(user=_AuthedUser(), school=object(), roles=["TEACHER"])
    with pytest.raises(ApiError) as excinfo:
        require_school_role(request, "SCHOOL_MANAGER")
    assert excinfo.value.code == "PERMISSION_DENIED"


def test_active_school_required_permission_raises_context_error():
    permission = ActiveSchoolRequired()
    request = _FakeRequest(user=_AuthedUser(), school=None, error="SCHOOL_SUSPENDED")
    with pytest.raises(ApiError) as excinfo:
        permission.has_permission(request, APIView())
    assert excinfo.value.code == "SCHOOL_SUSPENDED"


def test_school_role_required_factory_allows_and_denies():
    teacher_only = school_role_required("TEACHER")()
    ok_request = _FakeRequest(user=_AuthedUser(), school=object(), roles=["TEACHER"])
    assert teacher_only.has_permission(ok_request, APIView()) is True

    deny_request = _FakeRequest(user=_AuthedUser(), school=object(), roles=["COUNSELOR"])
    with pytest.raises(ApiError) as excinfo:
        teacher_only.has_permission(deny_request, APIView())
    assert excinfo.value.code == "PERMISSION_DENIED"
