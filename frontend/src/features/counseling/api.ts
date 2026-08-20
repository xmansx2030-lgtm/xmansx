/** الحالات الإرشادية وخطط المتابعة وطلبات المعلمين (م14).
 *
 * الواجهة ترسل نية فقط: لا `school` ولا `opened_by` ولا `assigned_counselor` ولا
 * أي لقطة — الخادم يبنيها من الجلسة (البند 101).
 */

import { apiRequest } from "@/api/client";
import type { Paginated } from "@/features/warnings/api";

export type CaseStatus =
  | "OPEN"
  | "UNDER_ASSESSMENT"
  | "FOLLOW_UP_ACTIVE"
  | "RESOLVED"
  | "CLOSED";

export const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  OPEN: "مفتوحة",
  UNDER_ASSESSMENT: "قيد الدراسة",
  FOLLOW_UP_ACTIVE: "متابعة جارية",
  RESOLVED: "تم التحسن",
  CLOSED: "مغلقة",
};

/** الانتقالات المسموحة — نسخة الواجهة تخفي ما سيرفضه الخادم (الخادم هو الحكم). */
export const NEXT_STATUSES: Record<CaseStatus, CaseStatus[]> = {
  OPEN: ["UNDER_ASSESSMENT", "FOLLOW_UP_ACTIVE"],
  UNDER_ASSESSMENT: ["FOLLOW_UP_ACTIVE", "RESOLVED"],
  FOLLOW_UP_ACTIVE: ["UNDER_ASSESSMENT", "RESOLVED"],
  RESOLVED: ["FOLLOW_UP_ACTIVE"],
  CLOSED: [],
};

export type SessionType =
  | "STUDENT_MEETING"
  | "PARENT_MEETING"
  | "PHONE_CALL"
  | "TEACHER_CONSULTATION"
  | "CASE_REVIEW"
  | "OTHER";

export const SESSION_TYPE_LABELS: Record<SessionType, string> = {
  STUDENT_MEETING: "مقابلة الطالب",
  PARENT_MEETING: "مقابلة ولي الأمر",
  PHONE_CALL: "اتصال هاتفي",
  TEACHER_CONSULTATION: "تشاور مع معلم",
  CASE_REVIEW: "مراجعة الحالة",
  OTHER: "أخرى",
};
export const SESSION_TYPES = Object.keys(SESSION_TYPE_LABELS) as SessionType[];

export type GoalType =
  | "ATTENDANCE"
  | "MORNING_LATENESS"
  | "PERIOD_LATENESS"
  | "ACADEMIC"
  | "CLASSROOM_BEHAVIOR"
  | "PARTICIPATION"
  | "CUSTOM";

export const GOAL_TYPE_LABELS: Record<GoalType, string> = {
  ATTENDANCE: "المواظبة",
  MORNING_LATENESS: "التأخر الصباحي",
  PERIOD_LATENESS: "التأخر عن الحصص",
  ACADEMIC: "الأداء الدراسي",
  CLASSROOM_BEHAVIOR: "السلوك الصفي",
  PARTICIPATION: "المشاركة",
  CUSTOM: "هدف مخصص",
};
export const GOAL_TYPES = Object.keys(GOAL_TYPE_LABELS) as GoalType[];

export type ActivityType =
  | "STUDENT_CHECK_IN"
  | "PARENT_CONTACT"
  | "TEACHER_OBSERVATION"
  | "ATTENDANCE_REVIEW"
  | "BEHAVIOR_OBSERVATION"
  | "FOLLOW_UP_MEETING"
  | "OTHER";

export const ACTIVITY_TYPE_LABELS: Record<ActivityType, string> = {
  STUDENT_CHECK_IN: "متابعة مع الطالب",
  PARENT_CONTACT: "تواصل مع ولي الأمر",
  TEACHER_OBSERVATION: "طلب ملاحظة معلم",
  ATTENDANCE_REVIEW: "مراجعة المواظبة",
  BEHAVIOR_OBSERVATION: "ملاحظة سلوكية",
  FOLLOW_UP_MEETING: "لقاء متابعة",
  OTHER: "أخرى",
};
export const ACTIVITY_TYPES = Object.keys(ACTIVITY_TYPE_LABELS) as ActivityType[];

export type RequestType =
  | "ACADEMIC_OBSERVATION"
  | "CLASSROOM_BEHAVIOR"
  | "PARTICIPATION"
  | "HOMEWORK"
  | "ATTENDANCE_OBSERVATION"
  | "CUSTOM";

export const REQUEST_TYPE_LABELS: Record<RequestType, string> = {
  ACADEMIC_OBSERVATION: "ملاحظة دراسية",
  CLASSROOM_BEHAVIOR: "سلوك صفي",
  PARTICIPATION: "المشاركة",
  HOMEWORK: "الواجبات",
  ATTENDANCE_OBSERVATION: "ملاحظة مواظبة",
  CUSTOM: "أخرى",
};
export const REQUEST_TYPES = Object.keys(REQUEST_TYPE_LABELS) as RequestType[];

export type TeacherImprovement = "IMPROVED" | "UNCHANGED" | "WORSE" | "NOT_ENOUGH_INFORMATION";
export const IMPROVEMENT_LABELS: Record<TeacherImprovement, string> = {
  IMPROVED: "تحسن",
  UNCHANGED: "بلا تغيير",
  WORSE: "تراجع",
  NOT_ENOUGH_INFORMATION: "معلومات غير كافية",
};

export const CLOSURE_REASONS: Record<string, string> = {
  GOALS_MET: "تحققت أهداف الخطة",
  IMPROVED: "تحسن الطالب",
  NO_LONGER_REQUIRES_FOLLOW_UP: "لم تعد المتابعة لازمة",
  TRANSFERRED: "انتقل الطالب",
  GRADUATED: "تخرج الطالب",
  REFERRED_EXTERNALLY: "أُحيل لجهة خارجية",
  OTHER: "سبب آخر",
};

export const CASE_IMPROVEMENT_LABELS: Record<string, string> = {
  IMPROVED: "تحسن",
  PARTIALLY_IMPROVED: "تحسن جزئي",
  UNCHANGED: "بلا تغيير",
  WORSENED: "تراجع",
  NOT_ASSESSED: "لم يقيّم",
};

export interface DashboardKpis {
  new_referrals: number;
  open_cases: number;
  under_assessment: number;
  follow_up_active: number;
  resolved: number;
  waiting_teacher_response: number;
  due_activities: number;
  closed_this_month: number;
}

export interface CaseRow {
  id: number;
  student_id: number;
  student_name: string;
  grade_name: string | null;
  section_name: string | null;
  status: CaseStatus;
  status_label: string;
  priority: string;
  priority_label: string;
  referral_id: number;
  referral_category: string;
  referral_category_label: string;
  referral_reason_label: string;
  counselor_name: string | null;
  counselor_membership_id: number | null;
  opened_at: string;
  last_activity_at: string;
  next_activity_due: string | null;
}

export interface CaseDetail extends CaseRow {
  summary: string;
  opened_by_name: string | null;
  closed_by_name: string | null;
  closed_at: string | null;
  closure_reason: string;
  outcome_summary: string;
  improvement_status: string;
  snapshot_at_opening: Record<string, unknown>;
  current_metrics: Record<string, unknown>;
  referral: {
    id: number;
    category_label: string;
    reason_label: string;
    description: string;
    created_at: string;
    snapshot_at_referral: Record<string, unknown>;
  };
  can_manage: boolean;
}

export interface SessionRow {
  id: number;
  session_type: SessionType;
  session_type_label: string;
  occurred_at: string;
  summary: string;
  observations: string;
  outcome: string;
  status: "RECORDED" | "VOIDED";
  status_label: string;
  created_by_name: string | null;
  void_reason: string;
}

export interface GoalRow {
  id: number;
  goal_type: GoalType;
  goal_type_label: string;
  title: string;
  description: string;
  baseline_value: number | null;
  target_value: number | null;
  unit: string;
  status: "OPEN" | "COMPLETED" | "CANCELLED";
  status_label: string;
  completed_at: string | null;
}

export interface ActivityRow {
  id: number;
  activity_type: ActivityType;
  activity_type_label: string;
  title: string;
  description: string;
  due_date: string | null;
  status: "PENDING" | "COMPLETED" | "CANCELLED";
  status_label: string;
  completed_at: string | null;
}

export interface PlanRow {
  id: number;
  title: string;
  status: "DRAFT" | "ACTIVE" | "COMPLETED" | "CANCELLED";
  status_label: string;
  start_date: string;
  target_end_date: string | null;
  notes: string;
  created_by_name: string | null;
  activated_at: string | null;
  completed_at: string | null;
  goals: GoalRow[];
  activities: ActivityRow[];
}

export interface TeacherRequestRow {
  id: number;
  request_type: RequestType;
  request_type_label: string;
  question: string;
  due_date: string | null;
  status: "PENDING" | "ANSWERED" | "CANCELLED";
  status_label: string;
  teacher_name?: string | null;
  requested_by_name: string | null;
  created_at: string;
  responded_at: string | null;
  student_name?: string;
  student_id?: number;
  response?: {
    observation: string;
    improvement_status: TeacherImprovement;
    improvement_status_label: string;
    notes: string;
    responded_by_name: string | null;
    created_at: string;
  };
}

export interface CaseEventRow {
  id: number;
  event_type: string;
  event_type_label: string;
  actor_name: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface StudentCounselingSummary {
  open_cases: number;
  total_cases: number;
  cases: {
    id: number;
    status: CaseStatus;
    status_label: string;
    opened_at: string;
    closed_at: string | null;
    counselor_name: string | null;
    last_activity_at: string;
    improvement_status: string | null;
  }[];
}

const base = "/counselor";

export const getCounselorDashboard = (signal?: AbortSignal) =>
  apiRequest<DashboardKpis>(`${base}/dashboard/`, { signal });

export const getCases = (
  params: { status?: string; category?: string; sort?: string; page?: number },
  signal?: AbortSignal,
) => {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.category) query.set("category", params.category);
  if (params.sort) query.set("sort", params.sort);
  if (params.page) query.set("page", String(params.page));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<Paginated<CaseRow>>(`${base}/cases/${suffix}`, { signal });
};

export const getCase = (caseId: number, signal?: AbortSignal) =>
  apiRequest<CaseDetail>(`${base}/cases/${caseId}/`, { signal });

export const openCaseFromReferral = (referralId: number) =>
  apiRequest<CaseRow>(`/referrals/${referralId}/open-case/`, { method: "POST", body: {} });

export const changeCaseStatus = (caseId: number, status: CaseStatus) =>
  apiRequest<CaseRow>(`${base}/cases/${caseId}/status/`, { method: "POST", body: { status } });

export const closeCase = (
  caseId: number,
  payload: { closure_reason: string; outcome_summary?: string; improvement_status?: string },
) => apiRequest<CaseRow>(`${base}/cases/${caseId}/close/`, { method: "POST", body: payload });

export const reopenCase = (caseId: number, reason: string) =>
  apiRequest<CaseRow>(`${base}/cases/${caseId}/reopen/`, { method: "POST", body: { reason } });

export const getSessions = (caseId: number, signal?: AbortSignal) =>
  apiRequest<SessionRow[]>(`${base}/cases/${caseId}/sessions/`, { signal });

export const addSession = (
  caseId: number,
  payload: {
    session_type: SessionType;
    summary: string;
    observations?: string;
    outcome?: string;
  },
) => apiRequest<SessionRow>(`${base}/cases/${caseId}/sessions/`, { method: "POST", body: payload });

export const getPlans = (caseId: number, signal?: AbortSignal) =>
  apiRequest<PlanRow[]>(`${base}/cases/${caseId}/plans/`, { signal });

export const createPlan = (
  caseId: number,
  payload: { title: string; start_date: string; target_end_date?: string; activate?: boolean },
) => apiRequest<PlanRow>(`${base}/cases/${caseId}/plans/`, { method: "POST", body: payload });

export const changePlanStatus = (planId: number, status: string) =>
  apiRequest<PlanRow>(`${base}/plans/${planId}/status/`, { method: "POST", body: { status } });

export const addGoal = (
  planId: number,
  payload: {
    goal_type: GoalType;
    title: string;
    baseline_value?: number | null;
    target_value?: number | null;
    unit?: string;
  },
) => apiRequest<GoalRow>(`${base}/plans/${planId}/goals/`, { method: "POST", body: payload });

export const updateGoalStatus = (goalId: number, status: string) =>
  apiRequest<GoalRow>(`${base}/goals/${goalId}/`, { method: "PATCH", body: { status } });

export const addActivity = (
  planId: number,
  payload: { activity_type: ActivityType; title: string; due_date?: string },
) =>
  apiRequest<ActivityRow>(`${base}/plans/${planId}/activities/`, {
    method: "POST",
    body: payload,
  });

export const completeActivity = (activityId: number) =>
  apiRequest<ActivityRow>(`${base}/activities/${activityId}/complete/`, { method: "POST" });

export const getCaseTeacherRequests = (caseId: number, signal?: AbortSignal) =>
  apiRequest<TeacherRequestRow[]>(`${base}/cases/${caseId}/teacher-requests/`, { signal });

export const requestTeacherFollowUp = (
  caseId: number,
  payload: {
    teacher_membership_id: number;
    request_type: RequestType;
    question: string;
    due_date?: string;
  },
) =>
  apiRequest<TeacherRequestRow>(`${base}/cases/${caseId}/teacher-requests/`, {
    method: "POST",
    body: payload,
  });

export const getCaseTimeline = (caseId: number, signal?: AbortSignal) =>
  apiRequest<CaseEventRow[]>(`${base}/cases/${caseId}/timeline/`, { signal });

export const getSchoolTeachers = (signal?: AbortSignal) =>
  apiRequest<{ membership_id: number; name: string }[]>(`${base}/teachers/`, { signal });

/** صندوق المعلم — طلباته هو فقط (بلا محتوى الحالة). */
export const getMyFollowUpRequests = (signal?: AbortSignal) =>
  apiRequest<TeacherRequestRow[]>("/teacher/follow-up-requests/", { signal });

export const respondToFollowUp = (
  requestId: number,
  payload: { observation: string; improvement_status: TeacherImprovement; notes?: string },
) =>
  apiRequest<TeacherRequestRow>(`/teacher/follow-up-requests/${requestId}/respond/`, {
    method: "POST",
    body: payload,
  });

export const getStudentCounseling = (studentId: number, signal?: AbortSignal) =>
  apiRequest<StudentCounselingSummary>(`/students/${studentId}/counseling/`, { signal });
