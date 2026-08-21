"""Generate deterministic synthetic data for isolated Phase 19 verification."""

import json
import math
import os
import secrets
import string
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.backends.db import SessionStore
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.models import (
    AcademicYear,
    AcademicYearStatus,
    BellPeriod,
    BellSchedule,
    SchoolWeekDay,
    Semester,
    SemesterStatus,
)
from accounts.models import User
from attendance.models import DailyAbsenceStatus, DailyAttendanceSummary, DailyCompleteness
from devices.models import AttendanceDevice, StudentDeviceIdentity
from devices.services import bridge as bridge_service
from memberships.models import SchoolMembership, SchoolMembershipRole, SchoolRole
from schools.models import School
from schools.settings_models import SchoolSettings
from students.models import Grade, Section, Student, StudentEnrollment
from subscriptions.models import EntitlementKey, SaaSPlan
from subscriptions.services import plans as plan_service
from subscriptions.services import subscriptions as subscription_service

SYNTHETIC_PASSWORD = "Phase19-Synthetic-Only-2026"  # noqa: S105 - disposable test data
PREFIX = "phase19-synthetic"


class Command(BaseCommand):
    help = "Generate repeatable synthetic Phase 19 load data"

    def add_arguments(self, parser):
        parser.add_argument("--schools", type=int, default=1, choices=(1, 10, 50, 100))
        parser.add_argument("--students", type=int, default=500)
        parser.add_argument("--staff", type=int, default=100)
        parser.add_argument("--history-days", type=int, default=30)
        parser.add_argument("--history-students", type=int, default=100)
        parser.add_argument("--output", default="phase19-data.json")

    def handle(self, *args, **options):
        if not settings.DEBUG and os.environ.get("PHASE19_SYNTHETIC_DATA_ALLOWED") != "true":
            raise CommandError("Set PHASE19_SYNTHETIC_DATA_ALLOWED=true in an isolated stack")

        schools = options["schools"]
        students = options["students"]
        staff = options["staff"]
        history_days = options["history_days"]
        history_students = options["history_students"]
        if students not in (0, 500, 1000, 3000, 5000):
            raise CommandError("--students must be 0, 500, 1000, 3000, or 5000")
        if staff < 1 or staff > 500:
            raise CommandError("--staff must be between 1 and 500")
        if history_days not in (0, 30, 90, 180, 365):
            raise CommandError("--history-days must be 0, 30, 90, 180, or 365")

        admin, _ = User.objects.get_or_create(
            mobile="+966519000000",
            defaults={
                "first_name": "Phase19",
                "last_name": "Platform",
                "is_staff": True,
                "is_superuser": True,
                "password": make_password(SYNTHETIC_PASSWORD),
            },
        )
        plan = self._plan(admin)
        payload = {
            "synthetic": True,
            "password": SYNTHETIC_PASSWORD,
            "platform_admin": admin.mobile,
            "platform_admin_session": self._session(admin),
            "platform_admin_csrf": self._csrf(),
            "schools": [],
        }
        for index in range(schools):
            self.stdout.write(f"Generating synthetic school {index + 1}/{schools}...")
            payload["schools"].append(
                self._school(index, plan, admin, students, staff, history_days, history_students)
            )

        path = Path(options["output"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Synthetic dataset written to {path}"))

    def _plan(self, admin):
        plan = SaaSPlan.objects.filter(code="phase19-load").first()
        entitlements = {
            EntitlementKey.MAX_STUDENTS: 100_000,
            EntitlementKey.MAX_STAFF: 10_000,
            EntitlementKey.MAX_DEVICES: 100,
            EntitlementKey.MAX_STORAGE_GB: 100,
            **{
                key: True
                for key in EntitlementKey.values
                if key
                not in {
                    EntitlementKey.MAX_STUDENTS,
                    EntitlementKey.MAX_STAFF,
                    EntitlementKey.MAX_DEVICES,
                    EntitlementKey.MAX_STORAGE_GB,
                }
            },
        }
        if plan is None:
            return plan_service.create_plan(
                actor=admin,
                code="phase19-load",
                name_ar="Phase 19 synthetic",
                entitlements=entitlements,
            )
        return plan

    @transaction.atomic
    def _school(self, index, plan, admin, student_count, staff_count, history_days,
                history_students):
        slug = f"{PREFIX}-{index + 1:03d}"
        if School.objects.filter(slug=slug).exists():
            raise CommandError(f"{slug} already exists; use a fresh Phase 19 database")
        school = School.objects.create(name=f"Phase 19 Synthetic {index + 1}", slug=slug)
        SchoolSettings.objects.create(school=school, city="Synthetic")
        subscription_service.activate(school=school, plan_id=plan.id, actor=admin)

        password_hash = make_password(SYNTHETIC_PASSWORD)
        role_users = self._users(index, staff_count, password_hash)
        User.objects.bulk_create(role_users)
        role_map = [
            (role_users[0], SchoolRole.SCHOOL_MANAGER),
            (role_users[1], SchoolRole.VICE_PRINCIPAL),
            (role_users[2], SchoolRole.COUNSELOR),
            *[(user, SchoolRole.TEACHER) for user in role_users[3:]],
        ]
        memberships = SchoolMembership.objects.bulk_create(
            [SchoolMembership(user=user, school=school) for user, _ in role_map]
        )
        SchoolMembershipRole.objects.bulk_create(
            [
                SchoolMembershipRole(membership=membership, role=role)
                for membership, (_, role) in zip(memberships, role_map, strict=True)
            ]
        )

        today = timezone.localdate()
        year = AcademicYear.objects.create(
            school=school,
            name="Phase 19 synthetic year",
            start_date=today - timedelta(days=365),
            end_date=today,
            status=AcademicYearStatus.ACTIVE,
        )
        Semester.objects.create(
            school=school,
            academic_year=year,
            name="Phase 19 semester",
            sequence=1,
            start_date=today - timedelta(days=180),
            end_date=today,
            status=SemesterStatus.ACTIVE,
        )
        grades = Grade.objects.bulk_create(
            [
                Grade(school=school, name=f"Synthetic grade {n}", code=f"G{n}", sequence=n)
                for n in range(1, 4)
            ]
        )
        section_count = max(3, math.ceil(max(student_count, 1) / 30))
        sections = Section.objects.bulk_create(
            [
                Section(
                    school=school,
                    grade=grades[i % len(grades)],
                    name=f"S{i + 1}",
                    code=f"S{i + 1}",
                )
                for i in range(section_count)
            ]
        )
        students = Student.objects.bulk_create(
            [
                Student(
                    school=school,
                    national_id_encrypted="",
                    national_id_lookup_hash=f"phase19-{index}-{i:08d}",
                    national_id_masked=f"******{i % 10000:04d}",
                    student_number=f"P19-{index}-{i:06d}",
                    full_name=f"Synthetic Student {index + 1}-{i + 1}",
                )
                for i in range(student_count)
            ],
            batch_size=1000,
        )
        StudentEnrollment.objects.bulk_create(
            [
                StudentEnrollment(
                    school=school,
                    student=student,
                    academic_year=year,
                    grade=sections[i % section_count].grade,
                    section=sections[i % section_count],
                    enrolled_at=today - timedelta(days=400),
                )
                for i, student in enumerate(students)
            ],
            batch_size=1000,
        )
        self._schedule(school)
        self._history(school, year, sections, students, history_days, history_students)

        device = AttendanceDevice.objects.create(
            school=school,
            name="Phase 19 simulator",
            vendor="SIMULATOR",
            serial_number=f"P19-{index + 1}",
        )
        StudentDeviceIdentity.objects.bulk_create(
            [
                StudentDeviceIdentity(
                    school=school,
                    device=device,
                    external_user_id=f"student-{student.id}",
                    display_name=student.full_name,
                    student=student,
                    status="MATCHED",
                )
                for student in students[: min(len(students), 5000)]
            ],
            batch_size=1000,
        )
        _, bridge_token = bridge_service.create_bridge(
            school=school, name="Phase 19 bridge", actor=admin
        )
        sessions = [self._session(user, school) for user in role_users]
        csrf_tokens = [self._csrf() for _ in role_users]
        return {
            "id": school.id,
            "manager": role_users[0].mobile,
            "vice_principal": role_users[1].mobile,
            "counselor": role_users[2].mobile,
            "teachers": [user.mobile for user in role_users[3:]],
            "sessions": {
                "manager": sessions[0],
                "vice_principal": sessions[1],
                "counselor": sessions[2],
                "teachers": sessions[3:],
            },
            "csrf": {
                "manager": csrf_tokens[0],
                "vice_principal": csrf_tokens[1],
                "counselor": csrf_tokens[2],
                "teachers": csrf_tokens[3:],
            },
            "pdf_sessions": [self._session(role_users[1], school) for _ in range(100)],
            "pdf_csrf": [self._csrf() for _ in range(100)],
            "section_ids": [section.id for section in sections],
            "student_ids": [student.id for student in students[:500]],
            "device_id": device.id,
            "bridge_token": bridge_token,
            "students": student_count,
            "staff": len(role_users),
            "history_days": history_days,
        }

    @staticmethod
    def _session(user, school=None):
        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        if school is not None:
            session["active_school_id"] = school.id
        session.create()
        return session.session_key

    @staticmethod
    def _csrf():
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(32))

    @staticmethod
    def _users(school_index, staff_count, password_hash):
        total = staff_count + 3
        base = 20_000_000 + school_index * 10_000
        return [
            User(
                mobile=f"+9665{base + i:08d}",
                first_name="Synthetic",
                last_name=f"User {school_index + 1}-{i + 1}",
                password=password_hash,
            )
            for i in range(total)
        ]

    @staticmethod
    def _schedule(school):
        now = datetime.now(ZoneInfo("Asia/Riyadh"))
        schedule = BellSchedule.objects.create(school=school, name="Phase 19 current schedule")
        BellPeriod.objects.create(
            school=school,
            bell_schedule=schedule,
            sequence=1,
            name="Synthetic current period",
            start_time=now.replace(hour=0, minute=1, second=0).time().replace(microsecond=0),
            end_time=now.replace(hour=23, minute=59, second=0).time().replace(microsecond=0),
        )
        py_to_school = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6}
        SchoolWeekDay.objects.create(
            school=school,
            weekday=py_to_school[now.weekday()],
            is_school_day=True,
            bell_schedule=schedule,
        )

    @staticmethod
    def _history(school, year, sections, students, days, history_students):
        if not days or not students:
            return
        now = timezone.now()
        rows = []
        sample = students[: min(history_students, len(students))]
        for offset in range(days):
            target = date.today() - timedelta(days=offset + 1)
            for index, student in enumerate(sample):
                absent = 7 if (index + offset) % 19 == 0 else 0
                late = 1 if not absent and (index + offset) % 11 == 0 else 0
                rows.append(
                    DailyAttendanceSummary(
                        school=school,
                        student=student,
                        academic_year=year,
                        section=sections[index % len(sections)],
                        attendance_date=target,
                        expected_periods=7,
                        submitted_periods=7,
                        absent_periods=absent,
                        late_periods=late,
                        present_periods=7 - absent - late,
                        total_late_minutes=late * 8,
                        excused_absent_periods=0,
                        unexcused_absent_periods=absent,
                        completeness_status=DailyCompleteness.COMPLETE,
                        absence_status=(
                            DailyAbsenceStatus.FULL if absent == 7 else DailyAbsenceStatus.NONE
                        ),
                        calculated_at=now,
                    )
                )
                if len(rows) >= 5000:
                    DailyAttendanceSummary.objects.bulk_create(rows, batch_size=1000)
                    rows.clear()
        if rows:
            DailyAttendanceSummary.objects.bulk_create(rows, batch_size=1000)
