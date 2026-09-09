"""Arabic display labels for stable school role codes."""

MASCULINE_ROLE_LABELS = {
    "SCHOOL_MANAGER": "مدير المدرسة",
    "VICE_PRINCIPAL": "الوكيل",
    "COUNSELOR": "المرشد الطلابي",
    "TEACHER": "معلم",
    "GATE_GUARD": "حارس البوابة",
}

FEMININE_ROLE_LABELS = {
    "SCHOOL_MANAGER": "مديرة المدرسة",
    "VICE_PRINCIPAL": "الوكيلة",
    "COUNSELOR": "المرشدة الطلابية",
    "TEACHER": "معلمة",
    "GATE_GUARD": "حارسة البوابة",
}


def school_role_label(role: str, school_type: str) -> str:
    labels = FEMININE_ROLE_LABELS if school_type == "GIRLS" else MASCULINE_ROLE_LABELS
    return labels.get(role, role)


def school_student_label(school_type: str, *, definite: bool = False) -> str:
    if school_type == "GIRLS":
        return "الطالبة" if definite else "طالبة"
    return "الطالب" if definite else "طالب"


def school_students_label(school_type: str) -> str:
    return "الطالبات" if school_type == "GIRLS" else "الطلاب"
