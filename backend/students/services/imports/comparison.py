"""مقارنة صفوف الملف مع قاعدة البيانات وتصنيفها.

تستخدم مرتين: عند بناء المعاينة، وعند الاعتماد (إعادة تحقق ضد stale preview).
المطابقة: hash الهوية أولًا، ثم student_number — الاسم وحده لا يطابق أبدًا.
"""

from students.models import EnrollmentStatus, Student, StudentEnrollment


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
        ).select_related("grade", "section")
    }

    summary = {
        "new": 0, "unchanged": 0, "updated": 0,
        "section_changed": 0, "grade_changed": 0,
        "errors": 0, "duplicates": 0,
    }
    grades_to_create: set[tuple[str, str, int]] = set()
    sections_to_create: set[tuple[str, str, str]] = set()  # (grade_code, section_code, name)
    matched_student_ids: set[int] = set()

    for row in normalized_rows:
        if "DUPLICATE_IN_FILE" in row["errors"]:
            row["status"] = "DUPLICATE_IN_FILE"
            summary["duplicates"] += 1
            continue
        if row["errors"]:
            row["status"] = "ERROR"
            summary["errors"] += 1
            continue

        student = None
        if row["national_id_hash"]:
            student = students_by_hash.get(row["national_id_hash"])
        if student is None and row["student_number"]:
            student = students_by_number.get(row["student_number"])

        if student is None:
            row["status"] = "NEW"
            row["matched_student_id"] = None
            summary["new"] += 1
            grades_to_create.add((row["grade_code"], row["grade_name"], row["grade_sequence"]))
            sections_to_create.add((row["grade_code"], row["section_code"], row["section_name"]))
            continue

        matched_student_ids.add(student.id)
        row["matched_student_id"] = student.id
        changes: dict = {}
        if student.full_name != row["full_name"]:
            changes["full_name"] = {"from": student.full_name, "to": row["full_name"]}
        if row["guardian_name"] and student.guardian_name != row["guardian_name"]:
            changes["guardian_name"] = {"from": student.guardian_name, "to": row["guardian_name"]}
        if row["guardian_mobile"] and student.guardian_mobile != row["guardian_mobile"]:
            changes["guardian_mobile"] = {"changed": True}  # لا أرقام في الـ metadata
        row["changes"] = changes

        enrollment = enrollments.get(student.id)
        if enrollment is None:
            # طالب معروف بلا قيد فعال هذا العام — سينشأ له قيد
            row["status"] = "SECTION_CHANGED"
            row["needs_enrollment"] = True
            row["previous_section"] = None
            summary["section_changed"] += 1
            grades_to_create.add((row["grade_code"], row["grade_name"], row["grade_sequence"]))
            sections_to_create.add((row["grade_code"], row["section_code"], row["section_name"]))
        elif enrollment.grade.code != row["grade_code"]:
            row["status"] = "GRADE_CHANGED"
            row["previous_section"] = str(enrollment.section)
            summary["grade_changed"] += 1
            grades_to_create.add((row["grade_code"], row["grade_name"], row["grade_sequence"]))
            sections_to_create.add((row["grade_code"], row["section_code"], row["section_name"]))
        elif enrollment.section.code != row["section_code"]:
            row["status"] = "SECTION_CHANGED"
            row["previous_section"] = str(enrollment.section)
            summary["section_changed"] += 1
            sections_to_create.add((row["grade_code"], row["section_code"], row["section_name"]))
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
        ).values_list("grade__code", "code")
    )
    will_create_grades = sorted(
        {(code, name) for code, name, _ in grades_to_create if code not in existing_grade_codes}
    )
    will_create_sections = sorted(
        {
            (grade_code, name)
            for grade_code, section_code, name in sections_to_create
            if (grade_code, section_code) not in existing_sections
        }
    )

    summary["missing_from_file"] = len(missing)
    summary["will_create_grades"] = [name for _, name in will_create_grades]
    summary["will_create_sections"] = [f"{g} / {n}" for g, n in will_create_sections]
    # قائمة الأسماء تُقتطع للعرض، لكن **المعرفات كاملة**: فلتر «غير الموجودين في آخر
    # ملف نور» يبنى عليها، فاقتطاعها كان يُخفي طلابًا فعليين في المدارس الكبيرة.
    summary["missing_ids"] = [entry["student_id"] for entry in missing]

    return {"rows": normalized_rows, "summary": summary, "missing": missing[:500]}
