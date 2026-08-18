"""تطبيع وتحقق وتصنيف صفوف استيراد المعلمين.

الخصوصية (بند 34/74/75): المطابقة مع الحسابات العالمية تتم فقط داخل هذا
الـ workflow المراقب والمسجل. التصنيف لا يكشف أبدًا مدارس المستخدم الأخرى
ولا أدواره فيها — فقط «يوجد حساب مرتبط بهذا الرقم وسيدعى للانضمام».
لا يوجد API بحث حر عن وجود جوال على المنصة.
"""

from django.core.exceptions import ValidationError

from accounts.mobile import mask_mobile, normalize_mobile
from accounts.models import User
from memberships.models import MembershipStatus, SchoolMembership, SchoolRole
from students.services.imports.normalization import normalize_digits, normalize_text

ERROR_MESSAGES = {
    "MISSING_NAME": "اسم المعلم مفقود.",
    "MISSING_MOBILE": "رقم الجوال مفقود.",
    "INVALID_MOBILE": "رقم الجوال غير صالح.",
    "DUPLICATE_MOBILE_IN_FILE": "رقم الجوال مكرر داخل الملف.",
}


def build_normalized_row(row_number: int, values: tuple, mapping: dict) -> dict:
    def cell(field: str):
        index = mapping.get(field)
        if index is None or index >= len(values):
            return None
        return values[index]

    errors: list[str] = []
    full_name = normalize_text(cell("full_name"))
    if not full_name:
        errors.append("MISSING_NAME")

    mobile = ""
    mobile_masked = ""
    raw_mobile = cell("mobile")
    if raw_mobile is None or normalize_digits(raw_mobile) == "":
        errors.append("MISSING_MOBILE")
    else:
        try:
            mobile = normalize_mobile(normalize_digits(raw_mobile))
            mobile_masked = mask_mobile(mobile)
        except ValidationError:
            errors.append("INVALID_MOBILE")

    employee_number = normalize_digits(cell("employee_number")) or None

    return {
        "row_number": row_number,
        "full_name": full_name,
        "mobile": mobile,
        "mobile_masked": mobile_masked,
        "employee_number": employee_number,
        "job_title": normalize_text(cell("job_title")),
        "errors": errors,
    }


def mark_duplicates_in_file(rows: list[dict]) -> None:
    seen: dict[str, list[dict]] = {}
    for row in rows:
        if row["mobile"]:
            seen.setdefault(row["mobile"], []).append(row)
    for group in seen.values():
        if len(group) > 1:
            for row in group:
                if "DUPLICATE_MOBILE_IN_FILE" not in row["errors"]:
                    row["errors"].append("DUPLICATE_MOBILE_IN_FILE")


def error_message_for(codes: list[str]) -> str:
    return " ".join(ERROR_MESSAGES.get(code, code) for code in codes)


def categorize_rows(school, normalized_rows: list[dict]) -> dict:
    """يصنف كل صف مقابل الواقع الحالي — يستخدم للمعاينة وإعادة التحقق عند الاعتماد."""
    mobiles = [r["mobile"] for r in normalized_rows if r["mobile"]]
    users_by_mobile = {u.mobile: u for u in User.objects.filter(mobile__in=mobiles)}
    memberships = {
        m.user_id: m
        for m in SchoolMembership.objects.filter(
            school=school, user__mobile__in=mobiles
        ).select_related("user").prefetch_related("roles", "staff_profile")
    }

    summary = {
        "new": 0, "invite": 0, "add_role": 0, "profile_update": 0,
        "unchanged": 0, "invitation_pending": 0, "manual": 0,
        "errors": 0, "duplicates": 0,
    }

    for row in normalized_rows:
        if "DUPLICATE_MOBILE_IN_FILE" in row["errors"]:
            row["status"] = "DUPLICATE_IN_FILE"
            summary["duplicates"] += 1
            continue
        if row["errors"]:
            row["status"] = "ERROR"
            summary["errors"] += 1
            continue

        user = users_by_mobile.get(row["mobile"])
        if user is None:
            row["status"] = "NEW"
            summary["new"] += 1
            continue

        membership = memberships.get(user.id)
        if membership is None:
            # حساب عالمي موجود — دعوة فقط، بلا أي تفاصيل عن مدارسه الأخرى
            row["status"] = "EXISTING_USER_INVITE"
            summary["invite"] += 1
            continue

        if membership.status == MembershipStatus.INVITED:
            row["status"] = "INVITATION_PENDING"
            summary["invitation_pending"] += 1
            continue
        if membership.status in (
            MembershipStatus.DECLINED, MembershipStatus.SUSPENDED, MembershipStatus.LEFT
        ):
            # لا إعادة دعوة تلقائية بصمت — إجراء صريح من الواجهة
            row["status"] = "NEEDS_MANUAL_ACTION"
            summary["manual"] += 1
            continue

        # عضوية ACTIVE
        has_teacher = SchoolRole.TEACHER in membership.role_codes()
        profile = getattr(membership, "staff_profile", None)
        profile_changed = profile is not None and (
            profile.display_name != row["full_name"]
            or (row["employee_number"] and profile.employee_number != row["employee_number"])
            or (row["job_title"] and profile.job_title != row["job_title"])
        )
        row["membership_id"] = membership.id

        if not has_teacher:
            row["status"] = "ADD_TEACHER_ROLE"
            summary["add_role"] += 1
        elif profile is None or profile_changed:
            row["status"] = "PROFILE_UPDATE"
            summary["profile_update"] += 1
        else:
            row["status"] = "EXISTING_UNCHANGED"
            summary["unchanged"] += 1

    return {"rows": normalized_rows, "summary": summary}
