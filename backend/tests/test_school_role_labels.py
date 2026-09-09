import pytest

from schools.role_labels import school_role_label, school_student_label, school_students_label


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("SCHOOL_MANAGER", "مديرة المدرسة"),
        ("VICE_PRINCIPAL", "الوكيلة"),
        ("COUNSELOR", "المرشدة الطلابية"),
        ("TEACHER", "معلمة"),
        ("GATE_GUARD", "حارسة البوابة"),
    ],
)
def test_girls_school_role_labels(role, expected):
    assert school_role_label(role, "GIRLS") == expected


def test_student_labels_follow_school_type():
    assert school_student_label("BOYS") == "طالب"
    assert school_student_label("BOYS", definite=True) == "الطالب"
    assert school_students_label("BOYS") == "الطلاب"
    assert school_student_label("GIRLS") == "طالبة"
    assert school_student_label("GIRLS", definite=True) == "الطالبة"
    assert school_students_label("GIRLS") == "الطالبات"
