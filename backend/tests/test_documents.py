"""اختبارات المستندات المولدة (م12) — اللقطة المجمدة، PDF حقيقي، إعادة الطباعة، الفشل.

توليد PDF يحتاج مكتبات النظام (Pango/Cairo) المثبتة في صورة الحاوية؛ التشغيل
المعتمد لهذه المرحلة داخل Docker حيث **لا يتخطى أي اختبار**. الحارس أدناه يمنع
انهيار التشغيل على مضيف تطوير بلا المكتبات فقط.
"""

import hashlib
from datetime import UTC, date, datetime, time, timedelta

import pytest
from django.template.loader import render_to_string
from django.utils import timezone as dj_timezone

from attendance.models import (
    DailyAbsenceStatus,
    DailyAttendanceSummary,
    DailyCompleteness,
)
from common.errors import ApiError
from devices.models import ArrivalSource, ArrivalStatus, SchoolArrival
from documents.models import DocumentStatus, DocumentType, GeneratedDocument
from documents.pdf import pdf_engine_available
from documents.render_assets import render_assets
from documents.services import snapshots as snapshot_service
from documents.services.generation import (
    generate_document,
    open_for_download,
    retry_document,
    void_document,
)
from memberships.models import MembershipStatus, SchoolRole
from staff.models import StaffProfile
from student_warnings.models import StudentWarning, WarningLevel, WarningRuleType, WarningStatus
from tests.excuse_env import DAY, DAY2, build_env, full_day_absent

pytestmark = pytest.mark.django_db

requires_pdf = pytest.mark.skipif(
    not pdf_engine_available(), reason="محرك PDF غير متوفر خارج الحاوية"
)


@pytest.fixture
def env(make_school, make_user, make_membership):
    school = make_school()
    environment = build_env(
        school=school,
        teacher_membership=make_membership(make_user("0550001300"), school, ["TEACHER"]),
        vice_membership=make_membership(make_user("0550001301"), school, ["VICE_PRINCIPAL"]),
        prefix="30400",
    )
    from schools.models import SchoolSettings

    SchoolSettings.objects.create(
        school=school,
        ministry_school_number="12345",
        city="الرياض",
        official_principal_name="خالد المدير",
    )
    return environment


def make_warning(
    env,
    student,
    *,
    level=WarningLevel.LEVEL_2,
    value=5,
    threshold=5,
    warning_type=WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE,
) -> StudentWarning:
    if warning_type == WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE:
        detail_rows = [
            {
                "date": (DAY + timedelta(days=offset)).isoformat(),
                "weekday": "الأحد",
                "status": "غياب يوم دراسي كامل بدون عذر",
            }
            for offset in range(value)
        ]
    else:
        detail_rows = [
            {
                "date": (DAY + timedelta(days=offset)).isoformat(),
                "weekday": "الأحد",
                "arrival_time": "07:18",
                "late_minutes": 13,
                "status": "تأخر عن بداية الدوام الصباحي",
            }
            for offset in range(value)
        ]
    return StudentWarning.objects.create(
        school=env["school"],
        student=student,
        academic_year=env["year"],
        warning_type=warning_type,
        level=level,
        status=WarningStatus.ISSUED,
        threshold_at_issue=threshold,
        metric_value_at_issue=value,
        student_name_snapshot=student.full_name,
        grade_name_snapshot="الأول الثانوي",
        section_name_snapshot="1",
        national_id_masked_snapshot=student.national_id_masked,
        full_absence_days_at_issue=value + 1,
        unexcused_full_absence_days_at_issue=value,
        excused_full_absence_days_at_issue=1,
        absent_periods_at_issue=40,
        unexcused_absent_periods_at_issue=35,
        morning_late_occurrences_at_issue=8,
        morning_late_minutes_at_issue=137,
        detail_rows_snapshot=detail_rows,
        issued_by_membership=env["vice"],
        issued_at=dj_timezone.now(),
    )


def generate(env, student, document_type, **kwargs):
    return generate_document(
        school=env["school"],
        membership=env["vice"],
        student=student,
        document_type=document_type,
        **kwargs,
    )


def pdf_text(document) -> str:
    from pypdf import PdfReader

    handle = open_for_download(document)
    reader = PdfReader(handle)
    return "\n".join(page.extract_text() for page in reader.pages)


def pdf_pages(document) -> int:
    from pypdf import PdfReader

    return len(PdfReader(open_for_download(document)).pages)


# ---------------------------------------------------------------- مستند الإنذار


@requires_pdf
def test_warning_document_is_ready_with_real_pdf(env):
    student = env["students"][0]
    warning = make_warning(env, student)
    document = generate(
        env, student, DocumentType.WARNING_LEVEL_2, warning_id=warning.id
    )
    assert document.status == DocumentStatus.READY
    assert document.size_bytes > 0
    assert document.mime_type == "application/pdf"
    assert document.template_key == "warning_level_2"
    assert document.template_version == "v2"
    assert document.snapshot_schema_version == 2
    handle = open_for_download(document)
    content = handle.read()
    assert content[:5] == b"%PDF-"
    assert hashlib.sha256(content).hexdigest() == document.checksum


def test_warning_v2_renders_absence_details_only(env):
    student = env["students"][0]
    warning = make_warning(env, student)
    snapshot = snapshot_service.warning_snapshot(
        school=env["school"], warning=warning, membership=env["vice"], title="إشعار"
    )
    html = render_to_string(
        "documents/warning_v2.html", {"data": snapshot, "assets": render_assets()}
    )
    assert "تفاصيل أيام الغياب المشمولة في الإنذار" in html
    assert "غياب يوم دراسي كامل بدون عذر" in html
    assert "وقت الحضور" not in html
    assert "مدة التأخر" not in html
    assert "تفاصيل حالات التأخر الصباحي" not in html


def test_warning_v2_renders_morning_late_details_only(env):
    student = env["students"][0]
    warning = make_warning(
        env,
        student,
        value=3,
        threshold=3,
        warning_type=WarningRuleType.MORNING_LATE_OCCURRENCES,
    )
    snapshot = snapshot_service.warning_snapshot(
        school=env["school"], warning=warning, membership=env["vice"], title="إشعار"
    )
    html = render_to_string(
        "documents/warning_v2.html", {"data": snapshot, "assets": render_assets()}
    )
    assert "تفاصيل حالات التأخر الصباحي المشمولة في الإنذار" in html
    assert "وقت الحضور" in html
    assert "مدة التأخر" in html
    assert "تفاصيل أيام الغياب المشمولة في الإنذار" not in html
    assert "غياب يوم دراسي كامل بدون عذر" not in html


def test_girls_school_document_uses_feminine_principal_and_student_labels(env):
    school = env["school"]
    school.school_type = "GIRLS"
    school.save(update_fields=["school_type"])
    warning = make_warning(env, env["students"][0])

    snapshot = snapshot_service.warning_snapshot(
        school=school, warning=warning, membership=env["vice"], title="إشعار"
    )
    html = render_to_string(
        "documents/warning_v2.html", {"data": snapshot, "assets": render_assets()}
    )

    assert snapshot["school"]["principal_role_label"] == "مديرة المدرسة"
    assert snapshot["school"]["student_definite_label"] == "الطالبة"
    assert "مديرة المدرسة" in html
    assert "ولي أمر الطالبة" in html
    assert "الطالب/ة" not in html


@pytest.mark.parametrize(
    ("school_type", "principal_role_label", "manager_name"),
    [
        ("BOYS", "مدير المدرسة", "أ. خالد العتيبي"),
        ("GIRLS", "مديرة المدرسة", "أ. نورة القحطاني"),
    ],
)
def test_warning_uses_active_manager_name_when_official_name_is_blank(
    env,
    make_membership,
    make_user,
    school_type,
    principal_role_label,
    manager_name,
):
    school = env["school"]
    school.school_type = school_type
    school.save(update_fields=["school_type"])
    school.settings.official_principal_name = ""
    school.settings.save(update_fields=["official_principal_name"])

    manager = make_membership(
        make_user("0550001390", first_name="اسم الحساب"),
        school,
        [SchoolRole.SCHOOL_MANAGER],
    )
    StaffProfile.objects.create(
        school=school,
        membership=manager,
        display_name=manager_name,
    )
    warning = make_warning(env, env["students"][0])

    snapshot = snapshot_service.warning_snapshot(
        school=school, warning=warning, membership=env["vice"], title="إشعار"
    )
    html = render_to_string(
        "documents/warning_v2.html", {"data": snapshot, "assets": render_assets()}
    )

    assert snapshot["school"]["principal_role_label"] == principal_role_label
    assert snapshot["school"]["principal_name"] == manager_name
    assert manager_name in html


def test_warning_prefers_configured_official_principal_name_over_membership(
    env, make_membership, make_user
):
    manager = make_membership(
        make_user("0550001391", first_name="مدير العضوية"),
        env["school"],
        [SchoolRole.SCHOOL_MANAGER],
    )
    StaffProfile.objects.create(
        school=env["school"],
        membership=manager,
        display_name="مدير العضوية",
    )

    snapshot = snapshot_service.warning_snapshot(
        school=env["school"],
        warning=make_warning(env, env["students"][0]),
        membership=env["vice"],
        title="إشعار",
    )

    assert snapshot["school"]["principal_name"] == "خالد المدير"


def test_warning_ignores_suspended_manager_when_resolving_principal_name(
    env, make_membership, make_user
):
    env["school"].settings.official_principal_name = ""
    env["school"].settings.save(update_fields=["official_principal_name"])
    make_membership(
        make_user("0550001392", first_name="مدير موقوف"),
        env["school"],
        [SchoolRole.SCHOOL_MANAGER],
        status=MembershipStatus.SUSPENDED,
    )
    active_manager = make_membership(
        make_user("0550001393", first_name="المدير الفعلي"),
        env["school"],
        [SchoolRole.SCHOOL_MANAGER],
    )

    snapshot = snapshot_service.warning_snapshot(
        school=env["school"],
        warning=make_warning(env, env["students"][0]),
        membership=env["vice"],
        title="إشعار",
    )

    assert snapshot["school"]["principal_name"] == active_manager.user.display_name


@requires_pdf
def test_warning_pdf_contains_issue_time_values_in_arabic(env):
    student = env["students"][0]
    warning = make_warning(env, student, value=5, threshold=5)
    document = generate(env, student, DocumentType.WARNING_LEVEL_2, warning_id=warning.id)
    text = pdf_text(document)
    assert any("؀" <= ch <= "ۿ" for ch in text)  # نص عربي فعلي لا مربعات
    assert "5" in text


@requires_pdf
def test_reprint_keeps_original_after_metrics_change(env):
    """السيناريو 155: يصدر عند 5 ثم يصبح الحالي 8 — الملف المخزن لا يتغير."""
    student = env["students"][0]
    warning = make_warning(env, student, value=5, threshold=5)
    document = generate(env, student, DocumentType.WARNING_LEVEL_2, warning_id=warning.id)
    original = open_for_download(document).read()
    original_checksum = document.checksum

    # الغياب الحالي يرتفع ويتغير القيد والاسم
    for day in (DAY, DAY2):
        full_day_absent(env, student, day=day)
    student.full_name = "اسم جديد تمامًا"
    student.save(update_fields=["full_name"])

    document.refresh_from_db()
    reprinted = open_for_download(document).read()
    assert reprinted == original
    assert document.checksum == original_checksum
    assert document.snapshot_data["warning"]["metric_value_at_issue"] == 5
    assert document.snapshot_data["student"]["name"] != "اسم جديد تمامًا"


def test_snapshot_keeps_placement_after_transfer(env):
    """البندان 106-107: الصف/الفصل/الاسم من لقطة الإنذار لا من القيد الحالي."""
    student = env["students"][0]
    warning = make_warning(env, student)
    snapshot = snapshot_service.warning_snapshot(
        school=env["school"], warning=warning, membership=env["vice"], title="إشعار"
    )
    assert snapshot["student"]["grade"] == "الأول الثانوي"
    assert snapshot["student"]["section"] == "1"
    assert snapshot["student"]["name"] == student.full_name

    student.full_name = "طالب منقول"
    student.save(update_fields=["full_name"])
    warning.refresh_from_db()
    again = snapshot_service.warning_snapshot(
        school=env["school"], warning=warning, membership=env["vice"], title="إشعار"
    )
    assert again["student"]["name"] != "طالب منقول"


def test_rule_change_does_not_touch_existing_document(env):
    """البند 105: تغيير عتبة القاعدة لاحقًا لا يمس المستند الصادر."""
    from student_warnings.services.rules import update_rules

    student = env["students"][0]
    warning = make_warning(env, student, threshold=5)
    snapshot = snapshot_service.warning_snapshot(
        school=env["school"], warning=warning, membership=env["vice"], title="إشعار"
    )
    update_rules(
        school=env["school"],
        actor=env["vice"].user,
        payload={
            WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE: {
                "is_enabled": True,
                "levels": {"LEVEL_1": 8, "LEVEL_2": 12, "LEVEL_3": 20},
            }
        },
    )
    assert snapshot["warning"]["threshold_at_issue"] == 5


def test_warning_document_does_not_recalculate_metrics(env, django_assert_max_num_queries):
    """البند 30: بناء لقطة الإنذار بلا أي استعلام مقاييس حضور."""
    student = env["students"][0]
    warning = make_warning(env, student)
    full_day_absent(env, student, day=DAY)  # بيانات حالية مختلفة تمامًا
    warning = StudentWarning.objects.select_related(
        "academic_year", "issued_by_membership__staff_profile", "issued_by_membership__user"
    ).get(id=warning.id)
    with django_assert_max_num_queries(3):
        snapshot = snapshot_service.warning_snapshot(
            school=env["school"], warning=warning, membership=env["vice"], title="إشعار"
        )
    assert snapshot["metrics_at_issue"]["unexcused_full_absence_days"] == 5


@requires_pdf
def test_double_generation_creates_single_primary_document(env):
    student = env["students"][0]
    warning = make_warning(env, student)
    generate(env, student, DocumentType.WARNING_LEVEL_2, warning_id=warning.id)
    with pytest.raises(ApiError) as exc:
        generate(env, student, DocumentType.WARNING_LEVEL_2, warning_id=warning.id)
    assert exc.value.code == "DOCUMENT_ALREADY_EXISTS"
    assert GeneratedDocument.objects.filter(warning=warning).count() == 1


@requires_pdf
def test_voided_document_frees_the_slot_for_a_new_original(env):
    student = env["students"][0]
    warning = make_warning(env, student)
    first = generate(env, student, DocumentType.WARNING_LEVEL_2, warning_id=warning.id)
    void_document(
        school=env["school"], membership=env["vice"], document=first, reason="خطأ إداري"
    )
    second = generate(env, student, DocumentType.WARNING_LEVEL_2, warning_id=warning.id)
    assert second.id != first.id
    first.refresh_from_db()
    assert first.status == DocumentStatus.VOIDED
    assert second.status == DocumentStatus.READY


def test_document_for_voided_warning_rejected(env):
    student = env["students"][0]
    warning = make_warning(env, student)
    warning.status = WarningStatus.VOIDED
    warning.save(update_fields=["status"])
    with pytest.raises(ApiError):
        generate(env, student, DocumentType.WARNING_LEVEL_2, warning_id=warning.id)


def test_warning_level_must_match_document_type(env):
    student = env["students"][0]
    warning = make_warning(env, student, level=WarningLevel.LEVEL_2)
    with pytest.raises(ApiError) as exc:
        generate(env, student, DocumentType.WARNING_LEVEL_1, warning_id=warning.id)
    assert exc.value.code == "VALIDATION_ERROR"


# ---------------------------------------------------------------- التعهد


@requires_pdf
def test_commitment_freezes_current_absence(env):
    """البندان 108-109: التعهد يأخذ الغياب الحالي، ثم لا يتغير بعد ازدياده."""
    student = env["students"][0]
    full_day_absent(env, student, day=DAY)
    full_day_absent(env, student, day=DAY2)
    document = generate(
        env,
        student,
        DocumentType.ATTENDANCE_COMMITMENT,
        from_date=DAY,
        to_date=DAY2,
    )
    assert document.snapshot_data["metrics"]["unexcused_full_absence_days"] == 2
    original = open_for_download(document).read()

    later = DAY2 + timedelta(days=7)
    _summary(env, student, later, status=DailyAbsenceStatus.FULL, unexcused=7)
    document.refresh_from_db()
    assert document.snapshot_data["metrics"]["unexcused_full_absence_days"] == 2
    assert open_for_download(document).read() == original


# ---------------------------------------------------------------- كشف الغياب


def _summary(env, student, day, *, status, absent=7, excused=0, unexcused=0):
    """صف ملخص جاهز — البناء المباشر أوضح من بذر جلسات كاملة لكل حالة يوم."""
    complete = status != DailyAbsenceStatus.UNDETERMINED
    return DailyAttendanceSummary.objects.create(
        school=env["school"],
        student=student,
        section=env["section"],
        academic_year=env["year"],
        attendance_date=day,
        absence_status=status,
        absent_periods=absent,
        excused_absent_periods=excused,
        unexcused_absent_periods=unexcused,
        expected_periods=7,
        submitted_periods=7 if complete else 3,
        present_periods=max(0, (7 if complete else 3) - absent),
        completeness_status=(
            DailyCompleteness.COMPLETE if complete else DailyCompleteness.INCOMPLETE
        ),
        calculated_at=dj_timezone.now(),
    )


def test_absence_report_classifies_every_day_kind(env):
    """البنود 110 و35-36: بعذر، بدون عذر، مختلط، وغير محسوم — كل بتصنيفه."""
    student = env["students"][0]
    base = date(2026, 8, 3)
    _summary(env, student, base, status=DailyAbsenceStatus.FULL, excused=7)
    _summary(env, student, base + timedelta(days=1), status=DailyAbsenceStatus.FULL, unexcused=7)
    _summary(
        env, student, base + timedelta(days=2),
        status=DailyAbsenceStatus.PARTIAL, absent=3, excused=2, unexcused=1,
    )
    _summary(
        env, student, base + timedelta(days=3),
        status=DailyAbsenceStatus.UNDETERMINED, absent=0,
    )
    snapshot = snapshot_service.absence_report_snapshot(
        school=env["school"],
        student=student,
        membership=env["vice"],
        from_date=base,
        to_date=base + timedelta(days=5),
    )
    classifications = [row["classification"] for row in snapshot["rows"]]
    assert classifications == ["EXCUSED", "UNEXCUSED", "MIXED", "UNDETERMINED"]
    # اليوم غير المحسوم لا يعد غيابًا كاملًا (البند 36)
    assert snapshot["totals"]["full_absence_days"] == 2
    assert snapshot["totals"]["undetermined_days"] == 1
    assert snapshot["rows"][3]["day_status_label"] == "بيانات التحضير غير مكتملة"


def test_absence_report_preserves_mixed_day_counts(env):
    """السيناريو 157: 3 حصص = 2 بعذر + 1 بدون عذر تبقى كما هي."""
    student = env["students"][0]
    day = date(2026, 8, 5)
    _summary(env, student, day, status=DailyAbsenceStatus.PARTIAL, absent=3, excused=2, unexcused=1)
    snapshot = snapshot_service.absence_report_snapshot(
        school=env["school"], student=student, membership=env["vice"],
        from_date=day, to_date=day,
    )
    assert snapshot["totals"]["absent_periods"] == 3
    assert snapshot["totals"]["excused_absent_periods"] == 2
    assert snapshot["totals"]["unexcused_absent_periods"] == 1


def test_absence_report_rejects_reversed_range(env):
    with pytest.raises(ApiError) as exc:
        snapshot_service.absence_report_snapshot(
            school=env["school"],
            student=env["students"][0],
            membership=env["vice"],
            from_date=date(2026, 8, 10),
            to_date=date(2026, 8, 1),
        )
    assert exc.value.code == "INVALID_REPORT_DATE_RANGE"


# ---------------------------------------------------------------- التأخر الصباحي


def _arrival(env, student, day, minutes, *, source=ArrivalSource.BIOMETRIC):
    return SchoolArrival.objects.create(
        school=env["school"],
        student=student,
        attendance_date=day,
        first_arrival_at=datetime.combine(day, time(7, 30), tzinfo=UTC),
        raw_late_minutes=minutes + 5,
        counted_late_minutes=minutes,
        status=ArrivalStatus.LATE,
        source=source,
    )


def test_morning_late_report_sums_occurrences_and_minutes(env):
    """السيناريو 156: 8 مرات و137 دقيقة = ساعتان و17 دقيقة."""
    student = env["students"][0]
    base = date(2026, 8, 2)
    minutes = [20, 15, 25, 10, 30, 12, 18, 7]  # المجموع 137
    for index, value in enumerate(minutes):
        _arrival(env, student, base + timedelta(days=index), value)
    snapshot = snapshot_service.morning_late_snapshot(
        school=env["school"], student=student, membership=env["vice"],
        from_date=base, to_date=base + timedelta(days=10),
    )
    assert snapshot["totals"]["occurrences"] == 8
    assert snapshot["totals"]["counted_late_minutes"] == 137
    assert snapshot["totals"]["duration"] == "2 ساعة و17 دقيقة"
    assert snapshot["rows"][0]["source_label"] == "جهاز"


def test_morning_report_excludes_on_time_arrivals(env):
    student = env["students"][0]
    SchoolArrival.objects.create(
        school=env["school"], student=student, attendance_date=DAY,
        first_arrival_at=datetime.combine(DAY, time(6, 50), tzinfo=UTC),
        raw_late_minutes=0, counted_late_minutes=0,
        status=ArrivalStatus.ON_TIME, source=ArrivalSource.BIOMETRIC,
    )
    snapshot = snapshot_service.morning_late_snapshot(
        school=env["school"], student=student, membership=env["vice"],
        from_date=DAY, to_date=DAY,
    )
    assert snapshot["totals"]["occurrences"] == 0


# ---------------------------------------------------------------- تقرير المواظبة


def test_attendance_report_uses_morning_lateness(env):
    student = env["students"][0]
    _arrival(env, student, DAY, 40)

    snapshot = snapshot_service.attendance_report_snapshot(
        school=env["school"], student=student, membership=env["vice"],
        from_date=DAY, to_date=DAY,
    )
    summary = snapshot["summary"]
    assert summary["morning_late_occurrences"] == 1
    assert summary["morning_late_minutes"] == 40


def test_attendance_report_has_no_counseling_data(env):
    """البند 45: لا إرشاد ولا إحالات في التقرير."""
    snapshot = snapshot_service.attendance_report_snapshot(
        school=env["school"], student=env["students"][0], membership=env["vice"],
        from_date=DAY, to_date=DAY2,
    )
    assert set(snapshot) >= {"summary", "warnings", "actions"}
    assert "counseling" not in snapshot
    assert "referrals" not in snapshot


def test_attendance_report_lists_warnings_and_actions(env):
    from student_actions.models import StudentActionType
    from student_actions.services import create_student_action

    student = env["students"][0]
    make_warning(env, student)
    create_student_action(
        school=env["school"], membership=env["vice"], student=student,
        action_type=StudentActionType.PARENT_CONTACT, notes="اتصال",
    )
    snapshot = snapshot_service.attendance_report_snapshot(
        school=env["school"], student=student, membership=env["vice"],
        from_date=DAY, to_date=DAY2,
    )
    assert len(snapshot["warnings"]) == 1
    assert snapshot["warnings"][0]["level_label"] == "الإنذار الثاني"
    assert len(snapshot["actions"]) == 1
    assert snapshot["actions"][0]["type_label"] == "التواصل مع ولي الأمر"


# ---------------------------------------------------------------- PDF


@requires_pdf
def test_long_report_produces_multipage_pdf(env):
    """البندان 53 و115: 120 صفًا تنتج مستندًا متعدد الصفحات بلا انهيار."""
    student = env["students"][0]
    base = date(2026, 8, 1)
    rows = []
    for index in range(120):
        rows.append(
            DailyAttendanceSummary(
                school=env["school"], student=student, section=env["section"],
                academic_year=env["year"], attendance_date=base + timedelta(days=index),
                absence_status=DailyAbsenceStatus.FULL, absent_periods=7,
                unexcused_absent_periods=7, expected_periods=7, submitted_periods=7,
                present_periods=0,
                completeness_status=DailyCompleteness.COMPLETE,
                calculated_at=dj_timezone.now(),
            )
        )
    DailyAttendanceSummary.objects.bulk_create(rows)
    document = generate(
        env, student, DocumentType.ABSENCE_DETAIL_REPORT,
        from_date=base, to_date=base + timedelta(days=130),
    )
    assert document.status == DocumentStatus.READY
    assert len(document.snapshot_data["rows"]) == 120
    assert pdf_pages(document) >= 3


@requires_pdf
def test_long_arabic_name_and_special_characters_do_not_break_template(env):
    student = env["students"][0]
    student.full_name = "عبد الرحمن بن عبد العزيز بن محمد آل عبد الله الشمري المطيري" * 2
    student.save(update_fields=["full_name"])
    document = generate(
        env, student, DocumentType.ATTENDANCE_COMMITMENT, from_date=DAY, to_date=DAY2
    )
    assert document.status == DocumentStatus.READY
    assert document.size_bytes > 0


@requires_pdf
def test_notes_are_escaped_not_executed(env):
    """البند 117: نص يحوي وسومًا يخرج كنص داخل المستند لا كـHTML."""
    from django.template.loader import render_to_string

    student = env["students"][0]
    warning = make_warning(env, student)
    warning.notes = "<script>alert(1)</script>"
    warning.save(update_fields=["notes"])
    document = generate(env, student, DocumentType.WARNING_LEVEL_2, warning_id=warning.id)
    html = render_to_string("documents/warning.html", {"data": document.snapshot_data})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


@requires_pdf
def test_generated_file_is_outside_media_root_and_has_no_public_url(env, settings):
    student = env["students"][0]
    document = generate(
        env, student, DocumentType.ATTENDANCE_COMMITMENT, from_date=DAY, to_date=DAY2
    )
    path = document.file.path
    assert str(settings.MEDIA_ROOT) not in path
    with pytest.raises(ValueError):
        _ = document.file.url


# ---------------------------------------------------------------- الفشل وإعادة المحاولة


def test_failed_generation_never_claims_ready(env, monkeypatch):
    """البند 120: فشل الرسم ينتج FAILED برمز آمن وبلا ملف."""
    import documents.services.generation as generation_module

    def boom(*args, **kwargs):
        raise RuntimeError("template exploded")

    monkeypatch.setattr(generation_module, "_render", boom)
    student = env["students"][0]
    document = generate(
        env, student, DocumentType.ATTENDANCE_COMMITMENT, from_date=DAY, to_date=DAY2
    )
    assert document.status == DocumentStatus.FAILED
    assert document.error_code == "DOCUMENT_RENDER_FAILED"
    assert not document.file
    with pytest.raises(ApiError) as exc:
        open_for_download(document)
    assert exc.value.code == "DOCUMENT_NOT_READY"


@requires_pdf
def test_retry_uses_stored_snapshot_not_current_data(env, monkeypatch):
    """البند 121: إعادة المحاولة ترسم اللقطة المخزنة ولا تقرأ بيانات الطالب الآن."""
    import documents.services.generation as generation_module

    calls = {"count": 0}
    original_render = generation_module._render

    def failing_once(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient")
        return original_render(*args, **kwargs)

    monkeypatch.setattr(generation_module, "_render", failing_once)
    student = env["students"][0]
    full_day_absent(env, student, day=DAY)
    document = generate(
        env, student, DocumentType.ATTENDANCE_COMMITMENT, from_date=DAY, to_date=DAY
    )
    assert document.status == DocumentStatus.FAILED
    frozen = document.snapshot_data

    # تتغير بيانات الطالب بين المحاولتين
    full_day_absent(env, student, day=DAY2)
    student.full_name = "اسم بعد الفشل"
    student.save(update_fields=["full_name"])

    retried = retry_document(
        school=env["school"], membership=env["vice"], document=document
    )
    assert retried.status == DocumentStatus.READY
    assert retried.snapshot_data == frozen
    assert retried.snapshot_data["student"]["name"] != "اسم بعد الفشل"


@requires_pdf
def test_retry_rejected_for_ready_document(env):
    student = env["students"][0]
    document = generate(
        env, student, DocumentType.ATTENDANCE_COMMITMENT, from_date=DAY, to_date=DAY2
    )
    with pytest.raises(ApiError) as exc:
        retry_document(school=env["school"], membership=env["vice"], document=document)
    assert exc.value.code == "DOCUMENT_NOT_READY"


@requires_pdf
def test_missing_stored_file_reports_error_without_regenerating(env):
    """البند 124: ملف مفقود ⇒ خطأ صريح، لا توليد صامت من البيانات الحالية."""
    student = env["students"][0]
    document = generate(
        env, student, DocumentType.ATTENDANCE_COMMITMENT, from_date=DAY, to_date=DAY2
    )
    import os

    os.remove(document.file.path)
    with pytest.raises(ApiError) as exc:
        open_for_download(document)
    assert exc.value.code == "DOCUMENT_FILE_MISSING"
    document.refresh_from_db()
    assert document.status == DocumentStatus.READY  # الحالة لم تزور


# ---------------------------------------------------------------- العزل والحذف


@requires_pdf
def test_documents_are_tenant_isolated(env, make_school, make_user, make_membership):
    other_school = make_school()
    other = build_env(
        school=other_school,
        teacher_membership=make_membership(make_user("0550001310"), other_school, ["TEACHER"]),
        vice_membership=make_membership(
            make_user("0550001311"), other_school, ["VICE_PRINCIPAL"]
        ),
        prefix="30500",
    )
    document = generate(
        env, env["students"][0], DocumentType.ATTENDANCE_COMMITMENT,
        from_date=DAY, to_date=DAY2,
    )
    with pytest.raises(ApiError) as exc:
        void_document(
            school=other["school"], membership=other["vice"], document=document, reason="x"
        )
    assert exc.value.code == "DOCUMENT_NOT_FOUND"

    # ولا يمكن إصدار مستند لطالب مدرسة أخرى بجلسة هذه المدرسة
    with pytest.raises(ApiError) as exc:
        generate_document(
            school=other["school"],
            membership=other["vice"],
            student=env["students"][0],
            document_type=DocumentType.ATTENDANCE_COMMITMENT,
            from_date=DAY,
            to_date=DAY2,
        )
    assert exc.value.status_code == 404


@requires_pdf
def test_purge_registers_documents_and_their_files(env):
    from students.services.purge import PURGE_STEPS, PURGE_STORAGE_COLLECTORS

    labels = [label for label, _ in PURGE_STEPS]
    assert "المستندات المولدة" in labels
    assert "الإجراءات الطلابية" in labels
    # المستندات قبل الإجراءات قبل الإنذارات (تبعيات PROTECT)
    assert labels.index("المستندات المولدة") < labels.index("الإجراءات الطلابية")
    assert labels.index("الإجراءات الطلابية") < labels.index("إنذارات الطالب")

    student = env["students"][0]
    generate(
        env, student, DocumentType.ATTENDANCE_COMMITMENT, from_date=DAY, to_date=DAY2
    )
    collected = [
        f for collector in PURGE_STORAGE_COLLECTORS for f in collector(student)
    ]
    assert any(f.name.endswith(".pdf") for f in collected)
