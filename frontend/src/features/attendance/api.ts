import { apiRequest } from "@/api/client";

// ---- الأنواع ----

export interface CurrentPeriod {
  sequence: number;
  name: string;
  start_time: string;
  end_time: string;
}

export interface CurrentPeriodResponse {
  period: CurrentPeriod | null;
  date: string;
}

export interface AttendanceSection {
  id: number;
  name: string;
  grade_name: string;
  students_count: number;
}

export interface RosterStudent {
  student_id: number;
  full_name: string;
  national_id_masked: string;
}

export type MarkStatus = "ABSENT" | "LATE";

export interface SessionMark {
  student_id: number;
  status: MarkStatus;
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

/** إدخال علامة — لا يوجد late_minutes: يحسبه الخادم حصرًا من بداية الحصة. */
export interface MarkInput {
  student_id: number;
  status: MarkStatus;
  arrival_time?: string | null;
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

export const startSession = (sectionId: number) =>
  apiRequest<AttendanceSessionData>("/attendance/sessions/start/", {
    method: "POST",
    body: { section_id: sectionId },
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
