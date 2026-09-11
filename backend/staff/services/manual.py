"""إضافة موظف يدويًا: حساب جديد بكلمة مؤقتة أو دعوة لحساب قائم."""

from django.db import IntegrityError, transaction

from accounts.models import User
from audit.models import AuditAction
from audit.services import record_event
from common.errors import ApiError
from memberships.models import (
    MembershipStatus,
    SchoolMembership,
    SchoolMembershipRole,
    SchoolRole,
)
from staff.models import StaffProfile, StaffSource
from staff.services.credentials import initial_password_from_mobile


@transaction.atomic
def create_staff(*, school, data: dict, actor, request=None) -> tuple[StaffProfile, str | None]:
    from subscriptions.entitlements import lock_school_capacity, require_capacity
    from subscriptions.models import EntitlementKey
    from subscriptions.usage import count_active_staff

    if data["role"] == SchoolRole.SCHOOL_MANAGER:
        raise ApiError(
            "SCHOOL_MANAGER_ASSIGNMENT_PLATFORM_ONLY",
            "لا يمكن إضافة مدير آخر من إدارة موظفي المدرسة. "
            "للمدرسة مدير واحد تتم إدارة حسابه من إدارة المنصة.",
            403,
        )

    mobile = data["mobile"]
    user = User.objects.filter(mobile=mobile).first()
    membership = (
        SchoolMembership.objects.filter(user=user, school=school).first() if user else None
    )
    if membership and hasattr(membership, "staff_profile"):
        raise ApiError("STAFF_ALREADY_EXISTS", "هذا الموظف مضاف إلى المدرسة مسبقًا.", 409)

    if membership is None:
        lock_school_capacity(school)
        require_capacity(
            school,
            EntitlementKey.MAX_STAFF,
            current=count_active_staff(school),
            adding=1,
        )

    employee_number = data.get("employee_number") or None
    if employee_number and StaffProfile.objects.filter(
        school=school, employee_number=employee_number
    ).exists():
        raise ApiError("EMPLOYEE_NUMBER_ALREADY_EXISTS", "الرقم الوظيفي مستخدم مسبقًا.", 409)

    temporary_password: str | None = None
    if user is None:
        temporary_password = initial_password_from_mobile(mobile)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    mobile=mobile,
                    password=temporary_password,
                    first_name=data["display_name"],
                    must_change_password=True,
                )
        except IntegrityError:
            user = User.objects.get(mobile=mobile)
            temporary_password = None

    if membership is None:
        membership = SchoolMembership.objects.create(
            user=user,
            school=school,
            status=MembershipStatus.ACTIVE if temporary_password else MembershipStatus.INVITED,
        )
        if temporary_password is None:
            record_event(
                AuditAction.SCHOOL_MEMBERSHIP_INVITED,
                request=request,
                actor=actor,
                school=school,
                target_type="SchoolMembership",
                target_id=membership.id,
                metadata={"source": "MANUAL"},
            )
    elif membership.status == MembershipStatus.LEFT:
        # عضوية تاريخية لموظف حُذف سابقًا: نعيده بدعوة جديدة دون إنشاء
        # عضوية مكررة أو المساس بحسابه العالمي.
        membership.status = MembershipStatus.INVITED
        membership.save(update_fields=["status", "updated_at"])
        record_event(
            AuditAction.SCHOOL_MEMBERSHIP_INVITED,
            request=request,
            actor=actor,
            school=school,
            target_type="SchoolMembership",
            target_id=membership.id,
            metadata={"source": "MANUAL", "readded": True},
        )

    SchoolMembershipRole.objects.get_or_create(membership=membership, role=data["role"])
    try:
        profile = StaffProfile.objects.create(
            school=school,
            membership=membership,
            display_name=data["display_name"],
            employee_number=employee_number,
            job_title=data.get("job_title", ""),
            source=StaffSource.MANUAL,
        )
    except IntegrityError as exc:
        raise ApiError("STAFF_ALREADY_EXISTS", "تعذر إنشاء الموظف؛ تحقق من البيانات.", 409) from exc

    record_event(
        AuditAction.STAFF_PROFILE_CREATED,
        request=request,
        actor=actor,
        school=school,
        target_type="SchoolMembership",
        target_id=membership.id,
        metadata={"source": "MANUAL", "role": data["role"]},
    )
    if data["role"] == SchoolRole.COUNSELOR:
        from staff.services.counselor_sections import set_counselor_sections

        set_counselor_sections(
            school=school,
            membership=membership,
            section_ids=data.get("counselor_section_ids"),
            actor=actor,
            confirm_reassignment=data.get("confirm_section_reassignment", False),
            request=request,
        )
    return profile, temporary_password
