"""Phase 8.6 comparison and safety tests."""

import pytest

from devices.models import AttendanceDevice, IdentityStatus, StudentDeviceIdentity
from devices.services.roster import (
    _stable_external_user_id,
    compare_device_roster,
    current_roster_version,
)
from students.models import StudentStatus
from tests.test_students_api import _enroll, _make_student


def _active_school_data(make_school):
    school = make_school()
    student = _make_student(school, "1012345678", "طالب نشط")
    enrollment = _enroll(school, student)
    device = AttendanceDevice.objects.create(school=school, name="بوابة الطلاب")
    return school, student, enrollment, device


@pytest.mark.django_db
def test_compare_classifies_matched_create_and_name_update(make_school):
    school, student, _, device = _active_school_data(make_school)
    second = _make_student(school, "1012345679", "طالب جديد")
    _enroll(school, second, code="2")
    StudentDeviceIdentity.objects.create(
        school=school,
        device=device,
        student=student,
        external_user_id=_stable_external_user_id(student),
        display_name="اسم قديم",
        status=IdentityStatus.MATCHED,
    )

    result = compare_device_roster(
        school=school,
        device=device,
        device_users=[
            {
                "external_user_id": _stable_external_user_id(student),
                "display_name": "اسم قديم",
            }
        ],
    )

    assert result["summary"]["update_count"] == 1
    assert result["summary"]["create_count"] == 1
    assert result["summary"]["delete_count"] == 0


@pytest.mark.django_db
def test_inactive_managed_student_is_delete_but_unknown_is_conflict(make_school):
    school, student, _, device = _active_school_data(make_school)
    external_id = _stable_external_user_id(student)
    StudentDeviceIdentity.objects.create(
        school=school,
        device=device,
        student=student,
        external_user_id=external_id,
        display_name=student.full_name,
        status=IdentityStatus.MATCHED,
    )
    student.status = StudentStatus.GRADUATED
    student.save(update_fields=["status"])

    result = compare_device_roster(
        school=school,
        device=device,
        device_users=[
            {"external_user_id": external_id, "display_name": student.full_name},
            {"external_user_id": "manual-99", "display_name": "إدخال يدوي"},
        ],
    )

    assert result["summary"]["delete_count"] == 1
    assert result["summary"]["conflict_count"] == 1


@pytest.mark.django_db
def test_active_student_missing_from_noor_is_still_create_candidate(make_school):
    school, student, _, device = _active_school_data(make_school)
    result = compare_device_roster(school=school, device=device, device_users=[])
    assert result["summary"]["create_count"] == 1
    assert student.status == StudentStatus.ACTIVE


@pytest.mark.django_db
def test_roster_version_changes_after_lifecycle_change(make_school):
    school, student, _, _ = _active_school_data(make_school)
    before = current_roster_version(school=school)
    student.status = StudentStatus.WITHDRAWN
    student.save(update_fields=["status"])
    assert current_roster_version(school=school) != before
