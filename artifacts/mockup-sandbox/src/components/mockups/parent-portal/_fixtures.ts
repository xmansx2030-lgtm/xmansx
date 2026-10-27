import type { Child, ParentDay } from "./_types";

// Synthetic preview data only. No production accounts, students, or API calls.
const completeDay: ParentDay = {
  date: "2026-10-27",
  absence_status: "NONE",
  completeness_status: "COMPLETE",
  expected_periods: 6,
  submitted_periods: 6,
  present_periods: 6,
  absent_periods: 0,
  excused_absent_periods: 0,
  unexcused_absent_periods: 0,
  updated_at: "2026-10-27T09:20:00Z",
};

export const demoChildren: Child[] = [
  {
    relation_id: 11,
    school: { id: 10, name: "مدرسة النور الابتدائية" },
    student: {
      id: 5,
      full_name: "أحمد محمد",
      grade_name: "الخامس الابتدائي",
      section_name: "٢",
      department: "",
    },
    status: "ACTIVE",
    today: completeDay,
    new_notifications: 0,
    required_actions: 0,
  },
  {
    relation_id: 12,
    school: { id: 20, name: "مدرسة الأمل المتوسطة" },
    student: {
      id: 6,
      full_name: "سارة محمد",
      grade_name: "الثاني المتوسط",
      section_name: "١",
      department: "",
    },
    status: "ACTIVE",
    today: {
      ...completeDay,
      absence_status: "UNDETERMINED",
      completeness_status: "INCOMPLETE",
      submitted_periods: 0,
      present_periods: 0,
      updated_at: "2026-10-27T06:10:00Z",
    },
    new_notifications: 2,
    required_actions: 1,
  },
  {
    relation_id: 13,
    school: { id: 30, name: "مدرسة الإتقان" },
    student: null,
    status: "PENDING",
    today: null,
    new_notifications: 0,
    required_actions: 0,
  },
];
