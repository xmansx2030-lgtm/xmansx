"""يولد ملفات نور xlsx لاختبارات E2E بهويات فريدة لكل تشغيل.

يكتب إلى frontend/e2e/fixtures/: noor-1.xlsx وnoor-2.xlsx وmeta.json.
التفرد يجعل كل تشغيل E2E حتميًا (جدد=8) دون تنظيف قاعدة البيانات.
"""

import json
import time
from pathlib import Path

from openpyxl import Workbook

HEADERS = ["رقم الهوية", "اسم الطالب", "الصف", "الفصل", "جوال ولي الأمر"]
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "frontend" / "e2e" / "fixtures"


def _write(path: Path, rows: list[list]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    tag = str(int(time.time()))[-6:]

    def nid(n: int) -> str:
        return f"1{tag}{n:03d}"

    def name(n: int) -> str:
        return f"طالب اختبار {tag}-{n:02d}"

    base_rows = [
        [nid(1), name(1), "الأول الثانوي", "1", "0551110001"],
        [nid(2), name(2), "الأول الثانوي", "1", ""],
        [nid(3), name(3), "الأول الثانوي", "1", ""],
        [nid(4), name(4), "الأول الثانوي", "2", ""],
        [nid(5), name(5), "الأول الثانوي", "2", ""],
        [nid(6), name(6), "الأول الثانوي", "2", ""],
        [nid(7), name(7), "الثاني الثانوي", "1", ""],
        [nid(8), name(8), "الثاني الثانوي", "1", ""],
    ]
    _write(FIXTURES_DIR / "noor-1.xlsx", base_rows)

    # التحديث: 01 ينتقل للفصل 2، 09 جديد، 08 مفقود من الملف، البقية بلا تغيير
    update_rows = [
        [nid(1), name(1), "الأول الثانوي", "2", "0551110001"],
        *base_rows[1:7],
        [nid(9), name(9), "الثاني الثانوي", "1", ""],
    ]
    _write(FIXTURES_DIR / "noor-2.xlsx", update_rows)

    # ---- ملفات المعلمين (المرحلة 5) — جوالات فريدة لكل تشغيل ----
    staff_headers = ["اسم المعلم", "رقم الجوال", "الرقم الوظيفي"]

    def teacher_mobile(n: int) -> str:
        return f"05{tag}{n:02d}"  # 05 + tag(6) + NN = 10 أرقام

    def teacher_name(n: int) -> str:
        return f"معلم تجربة {tag}-{n}"

    def _write_staff(path: Path, rows: list[list]) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(staff_headers)
        for row in rows:
            sheet.append(row)
        workbook.save(path)

    _write_staff(
        FIXTURES_DIR / "staff-a.xlsx",
        [
            [teacher_name(1), teacher_mobile(1), f"A-{tag}-1"],
            [teacher_name(2), teacher_mobile(2), f"A-{tag}-2"],
        ],
    )
    # مدرسة B: نفس جوال المعلم 1 (موجود → دعوة) + معلم جديد 3
    _write_staff(
        FIXTURES_DIR / "staff-b.xlsx",
        [
            [teacher_name(1), teacher_mobile(1), f"B-{tag}-1"],
            [teacher_name(3), teacher_mobile(3), f"B-{tag}-3"],
        ],
    )
    # مدرسة C: فهد المرشد (0550000004) يستورد كمعلم → إضافة دور
    _write_staff(
        FIXTURES_DIR / "staff-c.xlsx",
        [["فهد المرشد", "0550000004", f"C-{tag}-4"]],
    )

    # ---- ملفات دورة الحياة (المرحلة 4.1) — طلاب مستقلون عن بقية الـ specs ----
    def lc_nid(n: int) -> str:
        return f"2{tag}{n:03d}"  # إقامة تبدأ بـ 2 — لا تصادم مع nid()

    def lc_name(n: int) -> str:
        return f"طالب دورة {tag}-{n}"

    lifecycle_rows = [
        [lc_nid(1), lc_name(1), "الثالث الثانوي", "1", ""],
        [lc_nid(2), lc_name(2), "الثالث الثانوي", "1", ""],
        [lc_nid(3), lc_name(3), "الثالث الثانوي", "2", ""],
    ]
    _write(FIXTURES_DIR / "noor-3.xlsx", lifecycle_rows)
    # الملف التالي بلا الطالب 3 → «غير موجود في آخر ملف»
    _write(FIXTURES_DIR / "noor-3b.xlsx", lifecycle_rows[:2])

    # ---- ملف الحضور (المرحلة 6) — فصلان مستقلان "8" و"9" لاختبارات التحضير ----
    def att_nid(n: int) -> str:
        return f"1{tag}9{n:02d}"  # لا تصادم: nid يستخدم NNN بلا 9 في البادئة

    def att_name(n: int) -> str:
        return f"طالب حضور {tag}-{n}"

    # أكواد فصول فريدة لكل تشغيل — جلسة الحضور UNIQUE لكل (فصل، تاريخ، حصة)
    # فلو أعيد استخدام نفس الفصل لاصطدم التشغيل بجلسة التشغيل السابق المرسلة
    att_section_manual = f"8-{tag}"
    att_section_qr = f"9-{tag}"
    attendance_rows = [
        [att_nid(1), att_name(1), "الأول الثانوي", att_section_manual, ""],
        [att_nid(2), att_name(2), "الأول الثانوي", att_section_manual, ""],
        [att_nid(3), att_name(3), "الأول الثانوي", att_section_manual, ""],
        [att_nid(4), att_name(4), "الأول الثانوي", att_section_qr, ""],
        [att_nid(5), att_name(5), "الأول الثانوي", att_section_qr, ""],
    ]
    _write(FIXTURES_DIR / "noor-4.xlsx", attendance_rows)

    # ---- ملف المتابعة (المرحلة 7) — صف فريد لكل تشغيل ليعزل عدادات اللوحة
    # عبر فلتر الصف (KPIs تتبع الفلاتر — سلوك موثق)
    def mon_nid(n: int) -> str:
        return f"1{tag}8{n:02d}"  # بادئة 8 — لا تصادم مع بقية المولدات

    monitoring_grade = f"صف المتابعة {tag}"
    monitoring_sections = [f"M1-{tag}", f"M2-{tag}", f"M3-{tag}"]
    monitoring_rows = [
        [mon_nid(i * 2 + j), f"طالب متابعة {tag}-{i * 2 + j}", monitoring_grade, sec, ""]
        for i, sec in enumerate(monitoring_sections)
        for j in (1, 2)
    ]
    _write(FIXTURES_DIR / "noor-5.xlsx", monitoring_rows)

    # ---- ملف التحليلات (المرحلة 8) — صف فريد وفصلان: A1 (3 طلاب) وA2 (2)
    def ana_nid(n: int) -> str:
        return f"1{tag}7{n:02d}"  # بادئة 7 — لا تصادم مع بقية المولدات

    analytics_grade = f"صف التحليلات {tag}"
    ana_section_1 = f"T1-{tag}"
    ana_section_2 = f"T2-{tag}"
    ana_students_1 = [f"محمد تحليل {tag}", f"خالد تحليل {tag}", f"سعد تحليل {tag}"]
    ana_students_2 = [f"فهد تحليل {tag}", f"عمر تحليل {tag}"]
    analytics_rows = [
        [ana_nid(i + 1), name, analytics_grade, ana_section_1, ""]
        for i, name in enumerate(ana_students_1)
    ] + [
        [ana_nid(i + 4), name, analytics_grade, ana_section_2, ""]
        for i, name in enumerate(ana_students_2)
    ]
    _write(FIXTURES_DIR / "noor-6.xlsx", analytics_rows)

    meta = {
        "tag": tag,
        "analytics_grade": analytics_grade,
        "analytics_section_1": ana_section_1,
        "analytics_section_2": ana_section_2,
        "analytics_students_1": ana_students_1,
        "analytics_students_2": ana_students_2,
        "monitoring_grade": monitoring_grade,
        "monitoring_sections": monitoring_sections,
        "attendance_section_manual": att_section_manual,
        "attendance_section_qr": att_section_qr,
        "attendance_students": [att_name(1), att_name(2), att_name(3)],
        "attendance_qr_students": [att_name(4), att_name(5)],
        "lifecycle_prefix": f"طالب دورة {tag}",
        "lifecycle_missing": lc_name(3),
        "first_student": name(1),
        "moved_student": name(1),
        "missing_student": name(8),
        "new_student": name(9),
        "first_nid_last4": nid(1)[-4:],
        "first_nid_full": nid(1),
        "teacher1_name": teacher_name(1),
        "teacher1_mobile": teacher_mobile(1),
        "teacher2_name": teacher_name(2),
        "teacher3_name": teacher_name(3),
    }
    (FIXTURES_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), "utf-8")
    print(f"fixtures generated (tag={tag})")


if __name__ == "__main__":
    main()
