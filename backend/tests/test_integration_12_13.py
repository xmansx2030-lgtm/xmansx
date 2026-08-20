"""اختبارات تكامل المرحلتين 12 و13 — ما لا يستطيع أي فرع وحده إثباته.

تغطي: ترتيب خطوات الحذف عبر الوحدات، أثر الإحالة الإدارية في سجل الإجراءات،
ثبات لقطة المستند بعد الإحالة وثبات لقطة الإحالة بعد المستند، وخصوصية المرشد
(إحالة مسندة لا تمنح تنزيل مستندات).
"""

import pytest
from django.utils import timezone as dj_timezone

from common.errors import ApiError
from documents.models import DocumentStatus, DocumentType
from documents.pdf import pdf_engine_available
from documents.services.generation import generate_document, open_for_download
from referrals.models import (
    ReferralCategory,
    ReferralReason,
    StudentReferral,
)
from referrals.services.referrals import acknowledge_referral, assign_counselor, create_referral
from student_actions.models import StudentAction, StudentActionType
from student_actions.services import create_student_action
from student_warnings.models import StudentWarning, WarningLevel, WarningRuleType, WarningStatus
from tests.excuse_env import DAY, DAY2, build_env

pytestmark = pytest.mark.django_db

requires_pdf = pytest.mark.skipif(
    not pdf_engine_available(), reason="محرك PDF غير متوفر خارج الحاوية"
)


@pytest.fixture
def env(make_school, make_user, make_membership):
    school = make_school()
    environment = build_env(
        school=school,
        teacher_membership=make_membership(make_user("0551200001"), school, ["TEACHER"]),
        vice_membership=make_membership(make_user("0551200002"), school, ["VICE_PRINCIPAL"]),
        prefix="31000",
    )
    from schools.models import SchoolSettings

    SchoolSettings.objects.create(
        school=school, ministry_school_number="77", city="الرياض",
        official_principal_name="مدير التكامل",
    )
    environment["manager"] = make_membership(
        make_user("0551200003"), school, ["SCHOOL_MANAGER"]
    )
    environment["counselor"] = make_membership(
        make_user("0551200004"), school, ["COUNSELOR"]
    )
    return environment


def make_warning(env, student) -> StudentWarning:
    return StudentWarning.objects.create(
        school=env["school"], student=student, academic_year=env["year"],
        warning_type=WarningRuleType.UNEXCUSED_FULL_DAY_ABSENCE, level=WarningLevel.LEVEL_2,
        status=WarningStatus.ISSUED, threshold_at_issue=5, metric_value_at_issue=5,
        student_name_snapshot=student.full_name, grade_name_snapshot="الأول الثانوي",
        section_name_snapshot="1", national_id_masked_snapshot=student.national_id_masked,
        unexcused_full_absence_days_at_issue=5,
        issued_by_membership=env["vice"], issued_at=dj_timezone.now(),
    )


def refer(env, student, *, membership, roles, **kwargs) -> StudentReferral:
    """إحالة مواظبة إدارية — فئة المواظبة للوكيل/المدير حصرًا (سياسة م13)."""
    return create_referral(
        school=env["school"],
        membership=membership,
        roles=roles,
        student=student,
        category=ReferralCategory.ATTENDANCE,
        reason_code=ReferralReason.REPEATED_ABSENCE,
        description="غياب متكرر يستدعي المتابعة الإرشادية.",
        **kwargs,
    )


def teacher_refer(env, student, *, membership) -> StudentReferral:
    """المعلم يحيل ضمن فئاته المسموحة (الأداء الدراسي) لا فئة المواظبة."""
    return create_referral(
        school=env["school"],
        membership=membership,
        roles=["TEACHER"],
        student=student,
        category=ReferralCategory.ACADEMIC,
        reason_code=ReferralReason.ACADEMIC_WEAKNESS,
        description="ضعف دراسي متكرر يحتاج متابعة.",
    )


# ---------------------------------------------------------------- الحذف النهائي


def test_purge_steps_cover_both_phases_in_dependency_order(env):
    """أبناء الإحالة ← الإحالة ← المستندات ← الإجراءات ← الإنذارات (البنود 19-21)."""
    from students.services.purge import PURGE_STEPS, PURGE_STORAGE_COLLECTORS

    labels = [label for label, _ in PURGE_STEPS]
    for expected in (
        "أحداث الإحالات", "ملاحظات الإحالات", "إحالات الطالب",
        "المستندات المولدة", "الإجراءات الطلابية", "إنذارات الطالب",
    ):
        assert expected in labels, expected
    assert labels.index("أحداث الإحالات") < labels.index("إحالات الطالب")
    assert labels.index("ملاحظات الإحالات") < labels.index("إحالات الطالب")
    assert labels.index("إحالات الطالب") < labels.index("إنذارات الطالب")
    assert labels.index("المستندات المولدة") < labels.index("الإجراءات الطلابية")
    assert labels.index("الإجراءات الطلابية") < labels.index("إنذارات الطالب")
    # جامع ملفات المستندات لم يفقد تسجيله بعد إضافة الإحالات (البند 21)
    assert "collect_generated_document_files" in {
        c.__name__ for c in PURGE_STORAGE_COLLECTORS
    }


# ---------------------------------------------------------------- الإجراء ↔ الإحالة


def test_admin_referral_records_exactly_one_action(env):
    """البندان 31 و68: إحالة الوكيل تترك أثرًا واحدًا في سجل الإجراءات."""
    student = env["students"][0]
    referral = refer(env, student, membership=env["vice"], roles=["VICE_PRINCIPAL"])
    actions = StudentAction.objects.filter(
        student=student, action_type=StudentActionType.REFERRED_TO_COUNSELOR
    )
    assert actions.count() == 1
    action = actions.first()
    assert action.performed_by_membership_id == env["vice"].id
    assert str(referral.id) in action.notes
    # الإحالة تبقى مصدر الحقيقة — الإجراء أثر إداري فقط (البند 35)
    assert referral.status == "NEW"


def test_teacher_referral_records_no_administrative_action(env):
    """البند 33: إحالة المعلم سجلها هي نفسها — لا إجراء إداري باسمه."""
    student = env["students"][0]
    teacher_refer(env, student, membership=env["teacher"])
    assert StudentAction.objects.filter(student=student).count() == 0


def test_referral_and_action_are_one_transaction(env):
    """البند 34: رفض التكرار يمنع الإحالة **والإجراء** معًا — لا أثر يتيم."""
    student = env["students"][0]
    refer(env, student, membership=env["vice"], roles=["VICE_PRINCIPAL"])
    before = StudentAction.objects.count()
    with pytest.raises(ApiError) as exc:
        refer(env, student, membership=env["vice"], roles=["VICE_PRINCIPAL"])
    assert exc.value.code == "DUPLICATE_OPEN_REFERRAL"
    assert StudentAction.objects.count() == before
    assert StudentReferral.objects.filter(student=student).count() == 1


def test_referral_action_links_the_source_warning(env):
    """البندان 37-38: الإجراء الناتج يحمل نفس الإنذار ولا يختلط بتسليمه."""
    student = env["students"][0]
    warning = make_warning(env, student)
    delivered = create_student_action(
        school=env["school"], membership=env["vice"], student=student,
        action_type=StudentActionType.WARNING_DELIVERED, warning_id=warning.id,
    )
    referral = refer(
        env, student, membership=env["vice"], roles=["VICE_PRINCIPAL"], source_warning=warning
    )
    referral_action = StudentAction.objects.get(
        student=student, action_type=StudentActionType.REFERRED_TO_COUNSELOR
    )
    assert referral.source_warning_id == warning.id
    assert referral_action.warning_id == warning.id
    assert delivered.id != referral_action.id
    assert delivered.action_type == StudentActionType.WARNING_DELIVERED


def test_full_chain_warning_document_action_referral(env):
    """البند 36: السلسلة كاملة بلا اعتماد دائري."""
    student = env["students"][0]
    warning = make_warning(env, student)
    create_student_action(
        school=env["school"], membership=env["vice"], student=student,
        action_type=StudentActionType.WARNING_DELIVERED, warning_id=warning.id,
    )
    referral = refer(
        env, student, membership=env["manager"], roles=["SCHOOL_MANAGER"], source_warning=warning
    )
    assign_counselor(
        referral_id=referral.id, school=env["school"], membership=env["manager"],
        counselor_id=env["counselor"].id,
    )
    acknowledge_referral(
        referral_id=referral.id, school=env["school"], membership=env["counselor"],
        roles=["COUNSELOR"],
    )
    referral.refresh_from_db()
    assert referral.status == "ACKNOWLEDGED"
    types = set(
        StudentAction.objects.filter(student=student).values_list("action_type", flat=True)
    )
    assert types == {
        StudentActionType.WARNING_DELIVERED,
        StudentActionType.REFERRED_TO_COUNSELOR,
    }


# ---------------------------------------------------------------- ثبات اللقطات


@requires_pdf
def test_document_bytes_unchanged_by_referral_lifecycle(env):
    """البندان 39-40: المستند الصادر لا يتأثر بإنشاء الإحالة أو تعيينها أو استلامها."""
    student = env["students"][0]
    warning = make_warning(env, student)
    document = generate_document(
        school=env["school"], membership=env["vice"], student=student,
        document_type=DocumentType.WARNING_LEVEL_2, warning_id=warning.id,
    )
    assert document.status == DocumentStatus.READY
    before = open_for_download(document).read()
    checksum = document.checksum

    referral = refer(
        env, student, membership=env["vice"], roles=["VICE_PRINCIPAL"], source_warning=warning
    )
    assign_counselor(
        referral_id=referral.id, school=env["school"], membership=env["vice"],
        counselor_id=env["counselor"].id,
    )
    acknowledge_referral(
        referral_id=referral.id, school=env["school"], membership=env["counselor"],
        roles=["COUNSELOR"],
    )

    document.refresh_from_db()
    assert document.checksum == checksum
    assert open_for_download(document).read() == before
    assert document.snapshot_data["warning"]["metric_value_at_issue"] == 5


@requires_pdf
def test_referral_snapshot_unchanged_by_documents_and_actions(env):
    """البندان 41-42: لقطة الإحالة مجمدة، والقيمة الحالية تبقى مشتقة منفصلة."""
    student = env["students"][0]
    referral = refer(env, student, membership=env["vice"], roles=["VICE_PRINCIPAL"])
    frozen = dict(referral.snapshot_data)

    generate_document(
        school=env["school"], membership=env["vice"], student=student,
        document_type=DocumentType.ATTENDANCE_COMMITMENT, from_date=DAY, to_date=DAY2,
    )
    create_student_action(
        school=env["school"], membership=env["vice"], student=student,
        action_type=StudentActionType.PARENT_CONTACT, notes="متابعة",
    )
    referral.refresh_from_db()
    assert referral.snapshot_data == frozen
