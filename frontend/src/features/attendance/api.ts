import { apiRequest } from "@/api/client";

// ---- الأنواع ----

export interface CurrentPeriod {
  sequence: number;
  name: string;
  start_time: string;
  end_time: string;
  timezone: string;
}

export interface CurrentPeriodResponse {
  period: CurrentPeriod | null;
  date: string;
}

export interface AttendanceSection {
  id: number;
  name: string;
  grade_id?: number;
  grade_name: string;
  students_count: number;
}

export interface RosterStudent {
  student_id: number;
  full_name: string;
  national_id_masked: string;
}

/** حالات محفوظة سابقًا؛ LATE للقراءة التاريخية فقط. */
export type SessionMarkStatus = "ABSENT" | "LATE";

export interface SessionMark {
  student_id: number;
  status: SessionMarkStatus;
  arrival_time: string | null;
  late_minutes: number | null;
}

export interface AttendanceSessionData {
  id: number;
  status: "IN_PROGRESS" | "SUBMITTED";
  attendance_date: string;
  section: AttendanceSection;
  period: CurrentPeriod;
  submitted_by: string | null;
  submitted_at: string | null;
  can_edit: boolean;
  roster: RosterStudent[];
  marks: SessionMark[];
}

export interface AttendancePreview {
  attendance_date: string;
  section: AttendanceSection;
  period: CurrentPeriod;
  session: AttendanceSessionData | null;
}

export type AttendanceStartSource = "SECTION_LIST" | "QR" | "DIRECT_LINK";

/** الحاضر ضمني، لذلك الغائب هو العلامة الوحيدة التي يرسلها التحضير. */
export interface MarkInput {
  student_id: number;
  status: "ABSENT";
}

export interface QrInfo {
  section_id: number;
  section_name: string;
  grade_name: string;
  token: string;
  url_path: string;
}

// ---- الطلبات ----

export const getCurrentPeriod = (signal?: AbortSignal) =>
  apiRequest<CurrentPeriodResponse>("/attendance/current-period/", { signal });

export const getAttendanceSections = (signal?: AbortSignal) =>
  apiRequest<AttendanceSection[]>("/attendance/sections/", { signal });

export const getAttendancePreview = (sectionId: number, signal?: AbortSignal) =>
  apiRequest<AttendancePreview>(`/attendance/sections/${sectionId}/preview/`, { signal });

export const startSession = (sectionId: number, source: AttendanceStartSource) =>
  apiRequest<AttendanceSessionData>("/attendance/sessions/start/", {
    method: "POST",
    body: { section_id: sectionId, source },
  });

export const getSession = (sessionId: number, signal?: AbortSignal) =>
  apiRequest<AttendanceSessionData>(`/attendance/sessions/${sessionId}/`, { signal });

export const submitSession = (sessionId: number, marks: MarkInput[]) =>
  apiRequest<AttendanceSessionData>(`/attendance/sessions/${sessionId}/submit/`, {
    method: "POST",
    body: { marks },
  });

export const editSession = (sessionId: number, marks: MarkInput[], reason: string) =>
  apiRequest<AttendanceSessionData>(`/attendance/sessions/${sessionId}/`, {
    method: "PATCH",
    body: { marks, reason },
  });

export const resolveQr = (token: string) =>
  apiRequest<AttendanceSection>("/attendance/qr/resolve/", {
    method: "POST",
    body: { token },
  });

export const getSectionQr = (sectionId: number, signal?: AbortSignal) =>
  apiRequest<QrInfo>(`/sections/${sectionId}/qr/`, { signal });

export const rotateSectionQr = (sectionId: number) =>
  apiRequest<QrInfo>(`/sections/${sectionId}/qr/`, { method: "POST" });

// ---- لوحة المتابعة (المرحلة 7) — الحالة والتأخر من الخادم حصرًا ----

export type MonitoringAttendanceStatus = "SUBMITTED" | "IN_PROGRESS" | "NOT_STARTED";
export type TimelinessStatus = "ON_TIME" | "OVERDUE";

export interface MonitoringSection {
  section_id: number;
  section_name: string;
  grade_id: number;
  grade_name: string;
  students_count: number;
  attendance_status: MonitoringAttendanceStatus;
  timeliness_status: TimelinessStatus;
  started_at: string | null;
  submitted_at: string | null;
  minutes_overdue: number | null;
  teacher_name: string | null;
  session_id: number | null;
}

export interface MonitoringSummary {
  total: number;
  submitted: number;
  in_progress: number;
  not_started: number;
  overdue_total: number;
  overdue_submitted: number;
  overdue_in_progress: number;
  overdue_not_started: number;
}

export interface MonitoringResponse {
  school_time: string;
  date: string;
  period: CurrentPeriod | null;
  alert: { minutes: number; alert_at: string } | null;
  summary: MonitoringSummary | null;
  sections: MonitoringSection[];
}

export const getMonitoring = (signal?: AbortSignal) =>
  apiRequest<MonitoringResponse>("/attendance/monitoring/current/", { signal });

// ---- تحليلات الغياب (المرحلة 8) — بلا PII: لا هوية ولا بيانات ولي أمر ----

export type MatchMode = "ALL_ABSENT" | "ANY_ABSENT";

export interface PeriodName {
  sequence: number;
  name: string;
}

export interface AnalyticsStudent {
  student_id: number;
  full_name: string;
  grade_name: string;
  section_name: string;
  period_statuses: { sequence: number; status: "ABSENT" | "LATE" | "PRESENT" }[];
}

export interface IncompleteSection {
  section_id: number;
  section_name: string;
  grade_name: string;
  missing_sequences: number[];
  reason: string;
}

export interface MultiPeriodResponse {
  date: string;
  periods: PeriodName[];
  match: MatchMode;
  summary: {
    matching_students: number;
    complete_sections: number;
    incomplete_sections: number;
  };
  students: AnalyticsStudent[];
  incomplete_sections: IncompleteSection[];
  day_periods: PeriodName[];
  page: number;
  page_size: number;
  total_students: number;
}

export interface MultiPeriodParams {
  date: string;
  period_sequences: number[];
  match: MatchMode;
  grade_id?: number | null;
  section_id?: number | null;
  page?: number;
  page_size?: number;
}

export const postMultiPeriodAnalytics = (params: MultiPeriodParams) =>
  apiRequest<MultiPeriodResponse>("/attendance/analytics/multi-period/", {
    method: "POST",
    body: params,
  });

export interface DailyAnalyticsResponse {
  date: string;
  is_school_day: boolean;
  expected_periods: number;
  day_periods: PeriodName[];
  summary: {
    total_students: number;
    complete_students: number;
    incomplete_students: number;
    full_absent: number;
    partial_absent: number;
    no_absence: number;
    undetermined: number;
    late_students: number;
    late_occurrences: number;
    late_minutes: number;
  };
  students: {
    student_id: number;
    full_name: string;
    grade_name: string;
    section_name: string;
    absent_periods: number;
    late_periods: number;
    total_late_minutes: number;
    submitted_periods: number;
    expected_periods: number;
  }[];
  page: number;
  page_size: number;
  total_students_filtered: number;
}

export const getDailyAnalytics = (
  params: { date: string; status?: string; grade?: number | ""; page?: number },
  signal?: AbortSignal,
) => {
  const query = new URLSearchParams({ date: params.date });
  if (params.status) query.set("status", params.status);
  if (params.grade) query.set("grade", String(params.grade));
  if (params.page) query.set("page", String(params.page));
  return apiRequest<DailyAnalyticsResponse>(
    `/attendance/analytics/daily/?${query.toString()}`,
    { signal },
  );
};
