"""دورة حياة الإحالة: إنشاء، تعيين، استلام، ملاحظات، إغلاق، إلغاء.

قواعد ثابتة:
- الإحالة **طلب متابعة** لا إنذار ولا تشخيص — لا حقول تشخيص هنا ولا في الواجهة.
- المعلم ينشئ ولا يعيّن مرشدًا (بند 80)؛ التعيين للمدير/الوكيل.
- التكرار المفتوح لنفس (الطالب، الفئة) يُكشف ويُقترح بدله إضافة ملاحظة (بند 33).
- كل انتقال يسجل حدثًا في الخط الزمني (للعرض) وAudit (للأمان) — بلا نص كامل.
"""

from django.db import transaction
from django.utils import timezone as dj_timezone

from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from memberships.models import MembershipStatus, SchoolMembership, SchoolRole
from referrals.models import (
    CATEGORIES_BY_SOURCE,
    OPEN_STATUSES,
    REASONS_BY_CATEGORY,
    REASONS_REQUIRING_DESCRIPTION,
    ReferralCategory,
    ReferralEventType,
    ReferralSourceType,
    ReferralStatus,
    StudentReferral,
    StudentReferralContribution,
    StudentReferralEvent,
)
from referrals.services.snapshots import build_referral_snapshot
from student_actions.models import StudentActionType
from student_actions.services import create_student_action
from students.models import Student

#: من يملك تعيين المرشد وإغلاق الحالة
ASSIGN_ROLES = (SchoolRole.SCHOOL_MANAGER, SchoolRole.VICE_PRINCIPAL)


def resolve_source_type(roles) -> str:
    """دور المُحيل الأعلى صلاحية — يُجمّد كـsnapshot في الإحالة (بند 9)."""
    role_set = set(roles or [])
    if SchoolRole.SCHOOL_MANAGER in role_set:
        return ReferralSourceType.SCHOOL_MANAGER
    if SchoolRole.VICE_PRINCIPAL in role_set:
        return ReferralSourceType.VICE_PRINCIPAL
    if SchoolRole.TEACHER in role_set:
        return ReferralSourceType.TEACHER
    raise ApiError(
        "REFERRAL_PERMISSION_DENIED",
        "ليست لديك صلاحية إنشاء إحالة.",
        status_code=403,
    )


def validate_reason(*, source_type: str, category: str, reason_code: str, description: str):
    if category not in CATEGORIES_BY_SOURCE[source_type]:
        raise ApiError(
            "INVALID_REFERRAL_CATEGORY",
            "لا يمكنك الإحالة ضمن هذه الفئة.",
            details={"category": category},
        )
    if reason_code not in REASONS_BY_CATEGORY[category]:
        raise ApiError(
            "INVALID_REFERRAL_REASON",
            "السبب المحدد لا ينتمي إلى فئة الإحالة.",
            details={"category": category, "reason_code": reason_code},
        )
    if reason_code in REASONS_REQUIRING_DESCRIPTION and not description.strip():
        raise ApiError(
            "INVALID_REFERRAL_REASON",
            "اكتب وصفًا موجزًا للملاحظة عند اختيار «أخرى».",
            details={"field": "description"},
        )


def active_counselors(school):
    """عضويات المرشدين النشطة في المدرسة — مصدر التعيين الوحيد المسموح."""
    return (
        SchoolMembership.objects.filter(
            school=school,
            status=MembershipStatus.ACTIVE,
            roles__role=SchoolRole.COUNSELOR,
        )
        .select_related("user", "staff_profile")
        .distinct()
    )


def validate_counselor(*, school, counselor_id: int) -> SchoolMembership:
    """مرشد نشط في نفس المدرسة حصرًا — يمنع التعيين عبر المدارس (بند 83)."""
    counselor = active_counselors(school).filter(id=counselor_id).first()
    if counselor is None:
        raise ApiError(
            "INVALID_COUNSELOR_ASSIGNMENT",
            "المرشد المحدد غير نشط في المدرسة الحالية.",
            status_code=400,
        )
    return counselor


def find_open_duplicate(*, school, student, category: str) -> StudentReferral | None:
    """حالة مفتوحة لنفس الطالب والفئة — أساس اقتراح «أضف ملاحظة» بدل إحالة جديدة."""
    return (
        StudentReferral.objects.filter(
            school=school, student=student, category=category, status__in=OPEN_STATUSES
        )
        .select_related(
            "created_by_membership__user",
            "created_by_membership__staff_profile",
            "assigned_counselor_membership__user",
            "assigned_counselor_membership__staff_profile",
        )
        .order_by("-created_at")
        .first()
    )


def _log_event(*, referral, event_type: str, membership, metadata=None) -> None:
    StudentReferralEvent.objects.create(
        school=referral.school,
        referral=referral,
        event_type=event_type,
        actor_membership=membership,
        metadata_safe=metadata or {},
    )


def create_referral(
    *, school, membership, roles, student, category: str, reason_code: str,
    description: str = "", priority: str = "NORMAL", source_warning=None,
    assigned_counselor_id: int | None = None, allow_duplicate: bool = False,
    request=None,
) -> StudentReferral:
    source_type = resolve_source_type(roles)
    validate_reason(
        source_type=source_type,
        category=category,
        reason_code=reason_code,
        description=description,
    )

    can_assign = bool(set(roles or []) & set(ASSIGN_ROLES))
    if assigned_counselor_id is not None and not can_assign:
        # المعلم ينشئ ولا يعيّن — التعيين قرار إداري (بند 80)
        raise ApiError(
            "REFERRAL_PERMISSION_DENIED",
            "تعيين المرشد من صلاحية المدير أو الوكيل.",
            status_code=403,
        )
    # تجاوز التكرار قرار إداري — لكن المنع يقع عند وجود تكرار فعلي لا على الراية
    allow_duplicate = allow_duplicate and can_assign
    counselor = (
        validate_counselor(school=school, counselor_id=assigned_counselor_id)
        if assigned_counselor_id is not None
        else None
    )
    if source_warning is not None and (
        source_warning.school_id != school.id or source_warning.student_id != student.id
    ):
        raise ApiError(
            "INVALID_REFERRAL_REASON",
            "الإنذار المرتبط لا يخص هذا الطالب.",
            details={"field": "source_warning"},
        )

    with transaction.atomic():
        # قفل صف الطالب: فحص التكرار والإنشاء داخل نفس المعاملة، وإلا مرّ طلبان
        # متزامنان لنفس (الطالب، الفئة) من الفحص معًا وأنشآ حالتين مفتوحتين
        Student.objects.select_for_update().filter(id=student.id).first()
        if not allow_duplicate:
            duplicate = find_open_duplicate(
                school=school, student=student, category=category
            )
            if duplicate is not None:
                if not can_assign:
                    raise ApiError(
                        "DUPLICATE_OPEN_REFERRAL",
                        "يوجد للطالب ملف متابعة مفتوح في نفس الفئة.",
                        status_code=409,
                        details={
                            "existing_referral_id": duplicate.id,
                            "recommended_action": "ADD_CONTRIBUTION",
                        },
                    )
                raise ApiError(
                    "DUPLICATE_OPEN_REFERRAL",
                    "يوجد للطالب ملف متابعة مفتوح في نفس الفئة.",
                    status_code=409,
                    details={
                        "existing_referral_id": duplicate.id,
                        "recommended_action": "ADD_CONTRIBUTION",
                        "can_force": True,
                    },
                )

        referral = StudentReferral.objects.create(
            school=school,
            student=student,
            source_type=source_type,
            category=category,
            reason_code=reason_code,
            description=description.strip()[:1000],
            created_by_membership=membership,
            assigned_counselor_membership=counselor,
            source_warning=source_warning,
            priority=priority,
            snapshot_data=build_referral_snapshot(
                school=school, student=student, category=category
            ),
        )
        _log_event(
            referral=referral,
            event_type=ReferralEventType.CREATED,
            membership=membership,
            metadata={"category": category, "reason_code": reason_code},
        )
        if counselor is not None:
            _log_event(
                referral=referral,
                event_type=ReferralEventType.ASSIGNED,
                membership=membership,
                metadata={"counselor_membership_id": counselor.id},
            )
        # دمج م12+م13 (البنود 31-35): إحالة إدارية تترك أثرًا في سجل الإجراءات،
        # داخل **نفس المعاملة** فإما ينجحان معًا أو لا شيء. إحالة المعلم لا تنتج
        # إجراءً إداريًا: سجلها هو الإحالة نفسها. ومصدر الحقيقة يبقى الإحالة.
        if source_type != ReferralSourceType.TEACHER:
            create_student_action(
                school=school,
                membership=membership,
                student=student,
                action_type=StudentActionType.REFERRED_TO_COUNSELOR,
                warning_id=source_warning.id if source_warning is not None else None,
                notes=f"إحالة رقم {referral.id} — {ReferralCategory(category).label}"[:500],
                request=request,
            )

        record_event(
            AuditAction.REFERRAL_CREATED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="StudentReferral",
            target_id=referral.id,
            # أعداد ومعرفات فقط — نص الملاحظة يبقى في الإحالة نفسها (بند 86)
            metadata={
                "student_id": student.id,
                "category": category,
                "reason_code": reason_code,
                "assigned": counselor is not None,
            },
        )
    return referral


def assign_counselor(
    *, referral_id: int, school, membership, counselor_id: int, request=None
) -> StudentReferral:
    """تعيين أو تغيير المرشد — التاريخ محفوظ في الخط الزمني (بند 25)."""
    counselor = validate_counselor(school=school, counselor_id=counselor_id)
    with transaction.atomic():
        referral = StudentReferral.objects.select_for_update().get(
            id=referral_id, school=school
        )
        if referral.status in (ReferralStatus.CLOSED, ReferralStatus.CANCELLED):
            raise _terminal_error(referral)
        previous_id = referral.assigned_counselor_membership_id
        if previous_id == counselor.id:
            return referral  # لا حدث ولا Audit لتعيين لم يغيّر شيئًا
        referral.assigned_counselor_membership = counselor
        referral.save(update_fields=["assigned_counselor_membership", "updated_at"])

        reassigned = previous_id is not None
        _log_event(
            referral=referral,
            event_type=(
                ReferralEventType.REASSIGNED if reassigned else ReferralEventType.ASSIGNED
            ),
            membership=membership,
            metadata={
                "counselor_membership_id": counselor.id,
                "previous_counselor_membership_id": previous_id,
            },
        )
        record_event(
            AuditAction.REFERRAL_REASSIGNED if reassigned else AuditAction.REFERRAL_ASSIGNED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="StudentReferral",
            target_id=referral.id,
            metadata={"counselor_membership_id": counselor.id},
        )
    return referral


def acknowledge_referral(
    *, referral_id: int, school, membership, roles, request=None
) -> StudentReferral:
    """استلام المرشد للحالة: NEW → ACKNOWLEDGED.

    المرشد المعيّن وحده يستلم؛ مرشد آخر لا يسحب حالة زميله (بند 55).
    الحالة غير المعيّنة يستلمها أي مرشد نشط ويصبح هو المعيّن (مطالبة ذرية).
    """
    with transaction.atomic():
        referral = StudentReferral.objects.select_for_update().get(
            id=referral_id, school=school
        )
        if referral.status == ReferralStatus.ACKNOWLEDGED:
            raise ApiError(
                "REFERRAL_ALREADY_ACKNOWLEDGED",
                "تم استلام هذه الإحالة مسبقًا.",
                status_code=409,
            )
        if referral.status in (ReferralStatus.CLOSED, ReferralStatus.CANCELLED):
            raise _terminal_error(referral)

        is_counselor = SchoolRole.COUNSELOR in set(roles or [])
        assigned_id = referral.assigned_counselor_membership_id
        if assigned_id is not None and assigned_id != membership.id:
            raise ApiError(
                "REFERRAL_PERMISSION_DENIED",
                "هذه الإحالة معينة لمرشد آخر.",
                status_code=403,
            )
        if assigned_id is None:
            if not is_counselor:
                raise ApiError(
                    "REFERRAL_PERMISSION_DENIED",
                    "استلام الإحالة من صلاحية المرشد.",
                    status_code=403,
                )
            # المطالبة داخل نفس القفل — لا يستلم مرشدان نفس الحالة
            referral.assigned_counselor_membership = membership
            _log_event(
                referral=referral,
                event_type=ReferralEventType.ASSIGNED,
                membership=membership,
                metadata={"counselor_membership_id": membership.id, "claimed": True},
            )

        referral.status = ReferralStatus.ACKNOWLEDGED
        referral.accepted_at = dj_timezone.now()
        referral.save(
            update_fields=[
                "status",
                "accepted_at",
                "assigned_counselor_membership",
                "updated_at",
            ]
        )
        _log_event(
            referral=referral,
            event_type=ReferralEventType.ACKNOWLEDGED,
            membership=membership,
        )
        record_event(
            AuditAction.REFERRAL_ACKNOWLEDGED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="StudentReferral",
            target_id=referral.id,
        )
    return referral


def close_referral(
    *, referral_id: int, school, membership, reason: str, cancel: bool = False,
    creator_only: bool = False, request=None,
) -> StudentReferral:
    """إغلاق الحالة أو إلغاؤها — لا حذف نهائي من سير العمل اليومي (بند 20).

    ‏creator_only: إلغاء المنشئ لإحالته مسموح **قبل استلامها** فقط — بعد الاستلام
    صارت حالة يعمل عليها المرشد، وسحبها من تحته قرار إداري.
    """
    with transaction.atomic():
        referral = StudentReferral.objects.select_for_update().get(
            id=referral_id, school=school
        )
        if referral.status in (ReferralStatus.CLOSED, ReferralStatus.CANCELLED):
            raise _terminal_error(referral)
        if creator_only and referral.status != ReferralStatus.NEW:
            raise ApiError(
                "REFERRAL_ALREADY_ACKNOWLEDGED",
                "تم استلام الإحالة من المرشد — الإلغاء بعدها للإدارة.",
                status_code=409,
            )
        now = dj_timezone.now()
        referral.status = ReferralStatus.CANCELLED if cancel else ReferralStatus.CLOSED
        referral.closed_at = now
        referral.closed_by_membership = membership
        referral.closure_reason = reason.strip()[:300]
        referral.save(
            update_fields=[
                "status",
                "closed_at",
                "closed_by_membership",
                "closure_reason",
                "updated_at",
            ]
        )
        _log_event(
            referral=referral,
            event_type=(
                ReferralEventType.CANCELLED if cancel else ReferralEventType.CLOSED
            ),
            membership=membership,
        )
        record_event(
            AuditAction.REFERRAL_CLOSED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="StudentReferral",
            target_id=referral.id,
            metadata={"cancelled": cancel},
        )
    return referral


def add_contribution(
    *, referral_id: int, school, membership, observation_type: str, notes: str,
    request=None,
) -> StudentReferralContribution:
    """ملاحظة على حالة مفتوحة — الحالة المغلقة لا تستقبل ملاحظات جديدة."""
    with transaction.atomic():
        referral = StudentReferral.objects.select_for_update().get(
            id=referral_id, school=school
        )
        if referral.status not in OPEN_STATUSES:
            raise _terminal_error(referral)
        contribution = StudentReferralContribution.objects.create(
            school=school,
            referral=referral,
            created_by_membership=membership,
            observation_type=observation_type,
            notes=notes.strip()[:1000],
        )
        _log_event(
            referral=referral,
            event_type=ReferralEventType.CONTRIBUTION_ADDED,
            membership=membership,
            metadata={"observation_type": observation_type},
        )
        record_event(
            AuditAction.REFERRAL_CONTRIBUTION_ADDED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="StudentReferral",
            target_id=referral.id,
            metadata={"contribution_id": contribution.id},
        )
    return contribution


def _terminal_error(referral: StudentReferral) -> ApiError:
    if referral.status == ReferralStatus.CANCELLED:
        return ApiError(
            "REFERRAL_ALREADY_CLOSED", "هذه الإحالة ملغاة.", status_code=409
        )
    return ApiError("REFERRAL_ALREADY_CLOSED", "هذه الإحالة مغلقة.", status_code=409)
