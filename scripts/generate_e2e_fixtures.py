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

    meta = {
        "tag": tag,
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
