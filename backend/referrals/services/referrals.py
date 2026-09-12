"""دورة حياة الإحالة: توجيه للوكيل، معالجة أو تحويل، استلام، ثم إغلاق.

قواعد ثابتة:
- الإحالة **طلب متابعة** لا إنذار ولا تشخيص — لا حقول تشخيص هنا ولا في الواجهة.
- المعلم ينشئ فتُوجّه الإحالة للوكيل المسؤول عن صف الطالب أو فصله.
- المرشد لا يرى الحالة قبل أن يحوّلها إليه الوكيل المسؤول أو المدير.
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

#: الإدارة تملك الإشراف؛ الوكيل المسؤول وحده يعالج إحالات نطاقه.
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
        .order_by("staff_profile__display_name", "user__first_name", "id")
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


def active_vice_principals(school):
    return (
        SchoolMembership.objects.filter(
            school=school,
            status=MembershipStatus.ACTIVE,
            roles__role=SchoolRole.VICE_PRINCIPAL,
        )
        .select_related("user", "staff_profile")
        .order_by("staff_profile__display_name", "user__first_name", "id")
        .distinct()
    )


def validate_vice_principal(*, school, vice_principal_id: int) -> SchoolMembership:
    vice = active_vice_principals(school).filter(id=vice_principal_id).first()
    if vice is None:
        raise ApiError(
            "INVALID_VICE_PRINCIPAL_ASSIGNMENT",
            "الوكيل المحدد غير نشط في المدرسة الحالية.",
            status_code=400,
        )
    return vice


def assigned_counselor_for_student(*, school, student) -> SchoolMembership | None:
    """مرشد فصل القيد النشط الحالي، إن كان المرشد نفسه فعالًا."""
    from staff.models import CounselorSectionAssignment
    from students.models import EnrollmentStatus

    enrollment = (
        student.enrollments.filter(
            school=school,
            status=EnrollmentStatus.ACTIVE,
            academic_year__status="ACTIVE",
        )
        .select_related("section")
        .order_by("-enrolled_at", "-id")
        .first()
    )
    if enrollment is None:
        return None
    assignment = (
        CounselorSectionAssignment.objects.filter(
            school=school,
            section=enrollment.section,
            counselor_membership__status=MembershipStatus.ACTIVE,
            counselor_membership__roles__role=SchoolRole.COUNSELOR,
        )
        .select_related("counselor_membership")
        .first()
    )
    return assignment.counselor_membership if assignment else None


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
    assigned_vice = None
    route_metadata = None
    if source_type == ReferralSourceType.TEACHER:
        counselor = None
        initial_status = ReferralStatus.PENDING_VICE
    else:
        # الإحالة التي ينشئها الوكيل نفسه تعد تحت مراجعته بالفعل. تظل
        # إحالات المعلمين وحدها محجوبة عن المرشد حتى قرار الوكيل المسؤول.
        assigned_vice = membership if source_type == ReferralSourceType.VICE_PRINCIPAL else None
        counselor = (
            validate_counselor(school=school, counselor_id=assigned_counselor_id)
            if assigned_counselor_id is not None
            else assigned_counselor_for_student(school=school, student=student)
        )
        initial_status = (
            ReferralStatus.REFERRED
            if counselor is not None
            else ReferralStatus.UNDER_VICE_REVIEW
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
        if source_type == ReferralSourceType.TEACHER:
            from staff.services.vice_principal_scopes import responsible_vice_for_student

            assigned_vice, route_metadata = responsible_vice_for_student(
                school=school, student=student
            )
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
            assigned_vice_membership=assigned_vice,
            assigned_counselor_membership=counselor,
            source_warning=source_warning,
            priority=priority,
            status=initial_status,
            vice_reviewed_at=(
                dj_timezone.now()
                if source_type != ReferralSourceType.TEACHER
                else None
            ),
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
        if source_type == ReferralSourceType.TEACHER:
            _log_event(
                referral=referral,
                event_type=ReferralEventType.ROUTED_TO_VICE,
                membership=membership,
                metadata={
                    **(route_metadata or {}),
                    "vice_principal_membership_id": (
                        assigned_vice.id if assigned_vice else None
                    ),
                },
            )
        if counselor is not None:
            _log_event(
                referral=referral,
                event_type=ReferralEventType.FORWARDED_TO_COUNSELOR,
                membership=membership,
                metadata={
                    "counselor_membership_id": counselor.id,
                    "automatic": assigned_counselor_id is None,
                },
            )
        # دمج م12+م13 (البنود 31-35): إحالة إدارية تترك أثرًا في سجل الإجراءات،
        # داخل **نفس المعاملة** فإما ينجحان معًا أو لا شيء. إحالة المعلم لا تنتج
        # إجراءً إداريًا: سجلها هو الإحالة نفسها. ومصدر الحقيقة يبقى الإحالة.
        if source_type != ReferralSourceType.TEACHER and counselor is not None:
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
                "assigned_vice_membership_id": assigned_vice.id if assigned_vice else None,
                "routing_scope": (route_metadata or {}).get("scope_kind"),
            },
        )
    return referral


def assign_vice_principal(
    *, referral_id: int, school, membership, vice_principal_id: int, request=None
) -> StudentReferral:
    """معالجة استثناءات التوجيه بواسطة المدير مع حفظ التاريخ."""
    vice = validate_vice_principal(
        school=school, vice_principal_id=vice_principal_id
    )
    with transaction.atomic():
        referral = StudentReferral.objects.select_for_update().get(
            id=referral_id, school=school
        )
        if referral.status not in (
            ReferralStatus.PENDING_VICE,
            ReferralStatus.UNDER_VICE_REVIEW,
        ):
            raise ApiError(
                "INVALID_REFERRAL_STATUS_TRANSITION",
                "لا يمكن تغيير الوكيل بعد تحويل الإحالة للمرشد.",
                status_code=409,
            )
        previous_id = referral.assigned_vice_membership_id
        if previous_id == vice.id:
            return referral
        referral.assigned_vice_membership = vice
        referral.status = ReferralStatus.PENDING_VICE
        referral.vice_reviewed_at = None
        referral.save(
            update_fields=[
                "assigned_vice_membership",
                "status",
                "vice_reviewed_at",
                "updated_at",
            ]
        )
        _log_event(
            referral=referral,
            event_type=ReferralEventType.ROUTED_TO_VICE,
            membership=membership,
            metadata={
                "vice_principal_membership_id": vice.id,
                "previous_vice_principal_membership_id": previous_id,
                "manual": True,
            },
        )
        record_event(
            AuditAction.REFERRAL_REASSIGNED if previous_id else AuditAction.REFERRAL_ASSIGNED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="StudentReferral",
            target_id=referral.id,
            metadata={"target_role": "VICE_PRINCIPAL", "membership_id": vice.id},
        )
    return referral


def start_vice_review(
    *, referral_id: int, school, membership, is_manager: bool = False, request=None
) -> StudentReferral:
    """انتقال ذري يثبت أن الوكيل المسؤول بدأ معالجة الإحالة."""
    with transaction.atomic():
        referral = StudentReferral.objects.select_for_update().get(
            id=referral_id, school=school
        )
        if referral.status == ReferralStatus.UNDER_VICE_REVIEW:
            if is_manager or referral.assigned_vice_membership_id == membership.id:
                return referral
            raise ApiError(
                "REFERRAL_PERMISSION_DENIED", "هذه الإحالة من مسؤولية وكيل آخر.", 403
            )
        if referral.status != ReferralStatus.PENDING_VICE:
            raise ApiError(
                "INVALID_REFERRAL_STATUS_TRANSITION",
                "الإحالة ليست بانتظار مراجعة الوكيل.",
                status_code=409,
            )
        if (
            referral.source_type == ReferralSourceType.TEACHER
            and referral.assigned_vice_membership_id is None
        ):
            raise ApiError(
                "REFERRAL_VICE_PRINCIPAL_REQUIRED",
                "يجب إسناد الإحالة إلى وكيل مسؤول قبل بدء معالجتها.",
                status_code=409,
            )
        if not is_manager and referral.assigned_vice_membership_id != membership.id:
            raise ApiError(
                "REFERRAL_PERMISSION_DENIED", "هذه الإحالة من مسؤولية وكيل آخر.", 403
            )
        referral.status = ReferralStatus.UNDER_VICE_REVIEW
        referral.vice_reviewed_at = dj_timezone.now()
        referral.save(update_fields=["status", "vice_reviewed_at", "updated_at"])
        _log_event(
            referral=referral,
            event_type=ReferralEventType.VICE_REVIEW_STARTED,
            membership=membership,
        )
        record_event(
            AuditAction.REFERRAL_ACKNOWLEDGED,
            request=request,
            actor=membership.user,
            school=school,
            target_type="StudentReferral",
            target_id=referral.id,
            metadata={"stage": "VICE_REVIEW"},
        )
    return referral


def assign_counselor(
    *, referral_id: int, school, membership, counselor_id: int, roles=None, request=None
) -> StudentReferral:
    """تحويل الوكيل للمرشد أو إعادة تعيينه قبل استلامه، بصورة ذرية."""
    counselor = validate_counselor(school=school, counselor_id=counselor_id)
    with transaction.atomic():
        referral = StudentReferral.objects.select_for_update().get(
            id=referral_id, school=school
        )
        effective_roles = roles if roles is not None else membership.role_codes()
        is_manager = SchoolRole.SCHOOL_MANAGER in set(effective_roles)
        if (
            referral.source_type == ReferralSourceType.TEACHER
            and referral.assigned_vice_membership_id is None
        ):
            raise ApiError(
                "REFERRAL_VICE_PRINCIPAL_REQUIRED",
                "يجب إسناد الإحالة إلى وكيل مسؤول قبل تحويلها للمرشد.",
                status_code=409,
            )
        if not is_manager and referral.assigned_vice_membership_id != membership.id:
            raise ApiError(
                "REFERRAL_PERMISSION_DENIED", "هذه الإحالة من مسؤولية وكيل آخر.", 403
            )
        if referral.status not in (
            ReferralStatus.PENDING_VICE,
            ReferralStatus.UNDER_VICE_REVIEW,
            ReferralStatus.REFERRED,
        ):
            if referral.status in (ReferralStatus.CLOSED, ReferralStatus.CANCELLED):
                raise _terminal_error(referral)
            raise ApiError(
                "INVALID_REFERRAL_STATUS_TRANSITION",
                "لا يمكن تغيير المرشد بعد استلام الحالة.",
                status_code=409,
            )
        previous_id = referral.assigned_counselor_membership_id
        if previous_id == counselor.id and referral.status == ReferralStatus.REFERRED:
            return referral  # لا حدث ولا Audit لتعيين لم يغيّر شيئًا
        referral.assigned_counselor_membership = counselor
        referral.status = ReferralStatus.REFERRED
        if referral.vice_reviewed_at is None:
            referral.vice_reviewed_at = dj_timezone.now()
        referral.save(
            update_fields=[
                "assigned_counselor_membership",
                "status",
                "vice_reviewed_at",
                "updated_at",
            ]
        )

        reassigned = previous_id is not None
        _log_event(
            referral=referral,
            event_type=(
                ReferralEventType.REASSIGNED
                if reassigned
                else ReferralEventType.FORWARDED_TO_COUNSELOR
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
            metadata={
                "counselor_membership_id": counselor.id,
                "stage": "COUNSELOR",
            },
        )
        if not reassigned:
            create_student_action(
                school=school,
                membership=membership,
                student=referral.student,
                action_type=StudentActionType.REFERRED_TO_COUNSELOR,
                warning_id=referral.source_warning_id,
                notes=f"إحالة رقم {referral.id} — {referral.get_category_display()}"[:500],
                request=request,
            )
    return referral


def acknowledge_referral(
    *, referral_id: int, school, membership, roles, request=None
) -> StudentReferral:
    """استلام المرشد المعيّن للحالة بعد تحويل الوكيل فقط."""
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
        if referral.status != ReferralStatus.REFERRED:
            if referral.status in (ReferralStatus.CLOSED, ReferralStatus.CANCELLED):
                raise _terminal_error(referral)
            raise ApiError(
                "REFERRAL_NOT_FORWARDED",
                "لم يحوّل الوكيل هذه الإحالة إلى المرشد بعد.",
                status_code=409,
            )

        is_counselor = SchoolRole.COUNSELOR in set(roles or [])
        assigned_id = referral.assigned_counselor_membership_id
        if not is_counselor or assigned_id != membership.id:
            raise ApiError(
                "REFERRAL_PERMISSION_DENIED",
                "هذه الإحالة معينة لمرشد آخر.",
                status_code=403,
            )
        referral.status = ReferralStatus.ACKNOWLEDGED
        referral.accepted_at = dj_timezone.now()
        referral.save(
            update_fields=[
                "status",
                "accepted_at",
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
    creator_only: bool = False, roles=None, request=None,
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
        effective_roles = set(
            roles if roles is not None else membership.role_codes()
        )
        is_manager = SchoolRole.SCHOOL_MANAGER in effective_roles
        is_responsible_vice = (
            SchoolRole.VICE_PRINCIPAL in effective_roles
            and referral.assigned_vice_membership_id == membership.id
            and referral.status
            in (ReferralStatus.PENDING_VICE, ReferralStatus.UNDER_VICE_REVIEW)
        )
        is_assigned_counselor = (
            SchoolRole.COUNSELOR in effective_roles
            and referral.assigned_counselor_membership_id == membership.id
            and referral.status == ReferralStatus.ACKNOWLEDGED
        )
        is_creator_before_review = (
            referral.created_by_membership_id == membership.id
            and referral.status == ReferralStatus.PENDING_VICE
        )
        if creator_only and not is_creator_before_review:
            raise ApiError(
                "REFERRAL_ALREADY_ACKNOWLEDGED",
                "بدأت معالجة الإحالة — الإلغاء بعدها للإدارة.",
                status_code=409,
            )
        if cancel:
            permitted = is_manager or is_responsible_vice or is_creator_before_review
        else:
            permitted = is_manager or is_responsible_vice or is_assigned_counselor
        if not permitted:
            raise ApiError(
                "REFERRAL_PERMISSION_DENIED",
                "هذا الإجراء للمسؤول الحالي عن الإحالة فقط.",
                status_code=403,
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
