"""مقارنة صفوف الملف مع قاعدة البيانات وتصنيفها.

تستخدم مرتين: عند بناء المعاينة، وعند الاعتماد (إعادة تحقق ضد stale preview).
المطابقة: hash الهوية أولًا، ثم student_number — الاسم وحده لا يطابق أبدًا.
"""

from parents.contact_security import normalized_contact
from students.models import EnrollmentStatus, Student, StudentEnrollment, StudentStatus
from students.services.imports.normalization import normalize_text


def _name_key(value: str) -> str:
    return normalize_text(value).casefold()


def _possible_duplicate(enrollment: StudentEnrollment, row: dict) -> bool:
    if enrollment.grade.code != row["grade_code"]:
        return False
    row_guardian = _name_key(row["guardian_name"])
    existing_guardian = _name_key(enrollment.student.guardian_name)
    if row_guardian and existing_guardian:
        return row_guardian == existing_guardian
    return enrollment.section.code == row["section_code"]


def _section_identity(row: dict) -> tuple[str, str, str]:
    return row["grade_code"], row["section_code"], row.get("department", "")


def _section_candidate(row: dict) -> tuple[str, str, str, str]:
    grade_code, section_code, department = _section_identity(row)
    return grade_code, section_code, department, row["section_name"]


def categorize_rows(school, academic_year, normalized_rows: list[dict]) -> dict:
    """يصنف كل صف ويحسب الملخص وقائمة «موجود في النظام وغير موجود في الملف»."""
    hashes = [r["national_id_hash"] for r in normalized_rows if r["national_id_hash"]]
    numbers = [r["student_number"] for r in normalized_rows if r["student_number"]]

    students_by_hash = {
        s.national_id_lookup_hash: s
        for s in Student.objects.filter(school=school, national_id_lookup_hash__in=hashes)
    }
    students_by_number = {
        s.student_number: s
        for s in Student.objects.filter(school=school, student_number__in=numbers)
    }

    enrollments = {
        e.student_id: e
        for e in StudentEnrollment.objects.filter(
            school=school,
            academic_year=academic_year,
            status=EnrollmentStatus.ACTIVE,
        ).select_related("grade", "section", "student")
    }
    active_by_name: dict[str, list[StudentEnrollment]] = {}
    for enrollment in enrollments.values():
        if enrollment.student.status == StudentStatus.ACTIVE:
            active_by_name.setdefault(_name_key(enrollment.student.full_name), []).append(
                enrollment
            )

    summary = {
        "new": 0, "unchanged": 0, "updated": 0,
        "section_changed": 0, "grade_changed": 0,
        "errors": 0, "duplicates": 0, "auto_resolved_duplicates": 0,
    }
    grades_to_create: set[tuple[str, str, int]] = set()
    sections_to_create: set[tuple[str, str, str, str]] = set()  # grade, section, department, name
    matched_student_ids: set[int] = set()
    section_candidates = {
        (
            row["grade_code"], row["grade_name"],
            row["section_code"], row["section_name"], row.get("department", ""),
        )
        for row in normalized_rows
        if row.get("grade_code") and row.get("section_code")
    }

    for row in normalized_rows:
        row["errors"] = [
            code for code in row["errors"]
            if code not in {"IDENTITY_CONFLICT", "POSSIBLE_DUPLICATE", "MERGED_IDENTIFIER"}
        ]
        row.pop("possible_duplicate_masks", None)
        if row.get("auto_resolved_duplicate"):
            row["status"] = "AUTO_RESOLVED_DUPLICATE"
            row["errors"] = []
            summary["auto_resolved_duplicates"] += 1
            continue
        if "DUPLICATE_IN_FILE" in row["errors"]:
            row["status"] = "DUPLICATE_IN_FILE"
            summary["duplicates"] += 1
            continue
        if row["errors"]:
            row["status"] = "ERROR"
            summary["errors"] += 1
            continue

        by_identity = students_by_hash.get(row["national_id_hash"])
        by_number = students_by_number.get(row["student_number"])
        if (by_identity and by_number and by_identity.id != by_number.id) or (
            by_number and row["national_id_hash"]
            and by_number.national_id_lookup_hash != row["national_id_hash"]
        ):
            row["errors"].append("IDENTITY_CONFLICT")
            row["status"] = "ERROR"
            summary["errors"] += 1
            continue
        student = by_identity or by_number

        if student is not None and student.merged_into_id:
            row["errors"].append("MERGED_IDENTIFIER")
            row["status"] = "ERROR"
            summary["errors"] += 1
            continue

        if student is None:
            if not row["national_id_hash"]:
                if "MISSING_NATIONAL_ID" not in row["errors"]:
                    row["errors"].append("MISSING_NATIONAL_ID")
                row["status"] = "ERROR"
                summary["errors"] += 1
                continue
            possible_matches = [
                enrollment.student
                for enrollment in active_by_name.get(_name_key(row["full_name"]), [])
                if _possible_duplicate(enrollment, row)
            ]
            if possible_matches:
                row["possible_duplicate_masks"] = sorted({
                    candidate.national_id_masked for candidate in possible_matches
                })
                row["errors"].append("POSSIBLE_DUPLICATE")
                row["status"] = "ERROR"
                summary["errors"] += 1
                continue
            row["status"] = "NEW"
            row["matched_student_id"] = None
            summary["new"] += 1
            grades_to_create.add((row["grade_code"], row["grade_name"], row["grade_sequence"]))
            sections_to_create.add(_section_candidate(row))
            continue

        matched_student_ids.add(student.id)
        row["matched_student_id"] = student.id
        changes: dict = {}
        if student.full_name != row["full_name"]:
            changes["full_name"] = {"from": student.full_name, "to": row["full_name"]}
        if row["guardian_name"] and student.guardian_name != row["guardian_name"]:
            changes["guardian_name"] = {"from": student.guardian_name, "to": row["guardian_name"]}
        if row["guardian_mobile"] and (
            normalized_contact(student.guardian_mobile) != row["guardian_mobile"]
        ):
            changes["guardian_mobile"] = {"changed": True}  # لا أرقام في الـ metadata
        if row["student_number"] and student.student_number != row["student_number"]:
            changes["student_number"] = {"changed": True}
        row["changes"] = changes

        enrollment = enrollments.get(student.id)
        if enrollment is None:
            # طالب معروف بلا قيد فعال هذا العام — سينشأ له قيد
            row["status"] = "SECTION_CHANGED"
            row["needs_enrollment"] = True
            row["previous_section"] = None
            summary["section_changed"] += 1
            grades_to_create.add((row["grade_code"], row["grade_name"], row["grade_sequence"]))
            sections_to_create.add(_section_candidate(row))
        elif enrollment.grade.code != row["grade_code"]:
            row["status"] = "GRADE_CHANGED"
            row["previous_section"] = str(enrollment.section)
            summary["grade_changed"] += 1
            grades_to_create.add((row["grade_code"], row["grade_name"], row["grade_sequence"]))
            sections_to_create.add(_section_candidate(row))
        elif enrollment.section.code != row["section_code"] or (
            row.get("department") and enrollment.section.department != row["department"]
        ):
            row["status"] = "SECTION_CHANGED"
            row["previous_section"] = str(enrollment.section)
            summary["section_changed"] += 1
            sections_to_create.add(_section_candidate(row))
        elif changes:
            row["status"] = "EXISTING_UPDATED"
            summary["updated"] += 1
        else:
            row["status"] = "EXISTING_UNCHANGED"
            summary["unchanged"] += 1

    # الموجودون في النظام (قيد فعال هذا العام) وغير الموجودين في الملف — عرض فقط، لا حذف
    missing = [
        {"student_id": sid, "name": enrollment.student.full_name}
        for sid, enrollment in (
            (sid, e) for sid, e in enrollments.items() if sid not in matched_student_ids
        )
    ]

    # الصفوف/الفصول الموجودة فعلاً تستبعد من قائمة «سيتم إنشاؤه» (للمعاينة)
    from students.models import Grade, Section

    existing_grade_codes = set(
        Grade.objects.filter(
            school=school, code__in=[g[0] for g in grades_to_create]
        ).values_list("code", flat=True)
    )
    existing_sections = set(
        Section.objects.filter(
            school=school, grade__code__in=[s[0] for s in sections_to_create]
        ).values_list("grade__code", "code", "department")
    )
    will_create_grades = sorted(
        {(code, name) for code, name, _ in grades_to_create if code not in existing_grade_codes}
    )
    will_create_sections = sorted(
        {
            (grade_code, department, name)
            for grade_code, section_code, department, name in sections_to_create
            if (grade_code, section_code, department) not in existing_sections
        }
    )

    summary["missing_from_file"] = len(missing)
    summary["will_create_grades"] = [name for _, name in will_create_grades]
    summary["will_create_sections"] = [
        f"{g} / {d} / {n}" if d else f"{g} / {n}"
        for g, d, n in will_create_sections
    ]
    summary["section_candidates"] = [
        {
            "grade_code": grade_code,
            "grade_name": grade_name,
            "section_code": section_code,
            "section_name": section_name,
            "department": department,
        }
        for grade_code, grade_name, section_code, section_name, department in sorted(
            section_candidates
        )
    ]
    # قائمة الأسماء تُقتطع للعرض، لكن **المعرفات كاملة**: فلتر «غير الموجودين في آخر
    # ملف نور» يبنى عليها، فاقتطاعها كان يُخفي طلابًا فعليين في المدارس الكبيرة.
    summary["missing_ids"] = [entry["student_id"] for entry in missing]

    return {"rows": normalized_rows, "summary": summary, "missing": missing[:500]}
