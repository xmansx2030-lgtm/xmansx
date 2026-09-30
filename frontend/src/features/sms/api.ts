import { apiRequest } from "@/api/client";

export type SmsProvider = "DREAMS" | "MSEGAT";
export type AbsenceSmsStatus = "QUEUED" | "SENDING" | "ACCEPTED" | "FAILED" | "UNKNOWN";

export interface SmsIntegration {
  provider: SmsProvider | null;
  username: string;
  sender_name: string;
  is_active: boolean;
  has_secret: boolean;
}

export interface AbsenceSmsCandidate {
  student_id: number;
  full_name: string;
  grade_name: string;
  section_name: string;
  absence_status: "FULL";
  submitted_periods: number;
  expected_periods: number;
  eligibility_reason: "NO_APPROVED_ATTENDANCE" | "EXCUSED_ABSENCE" | "MISSING_RECIPIENT" | "INVALID_RECIPIENT" | null;
  recipient_masked: string;
  send_status: AbsenceSmsStatus | null;
  send_error: string;
}

export interface AbsenceSmsContactIssue {
  student_id: number;
  full_name: string;
  grade_name: string;
  section_name: string;
  reason: "MISSING_RECIPIENT" | "INVALID_RECIPIENT";
}

export interface AbsenceSmsPreview {
  date: string;
  page: number;
  page_size: number;
  total: number;
  ready_total: number;
  candidate_student_ids: number[];
  selectable_student_ids: number[];
  contact_issues: AbsenceSmsContactIssue[];
  message_template: string;
  default_message_template: string;
  integration: Pick<SmsIntegration, "provider" | "sender_name" | "is_active">;
  students: AbsenceSmsCandidate[];
}

export interface StudentSmsHistoryItem {
  id: number;
  attendance_date: string;
  provider: SmsProvider;
  recipient_masked: string;
  status: AbsenceSmsStatus;
  message_text: string;
  requested_at: string;
  attempted_at: string | null;
  accepted_at: string | null;
  attempts: number;
}

export interface StudentSmsHistory {
  count: number;
  next: string | null;
  previous: string | null;
  results: StudentSmsHistoryItem[];
}

export const PROVIDER_LABELS: Record<SmsProvider, string> = {
  DREAMS: "دريمز",
  MSEGAT: "مسجات",
};

export const getSmsIntegration = (signal?: AbortSignal) =>
  apiRequest<SmsIntegration>("/school/sms/integration/", { signal });

export const saveSmsIntegration = (data: {
  provider: SmsProvider;
  username: string;
  api_key: string;
  sender_name: string;
  is_active: boolean;
}) => apiRequest<SmsIntegration>("/school/sms/integration/", { method: "PUT", body: data });

export const getAbsenceSmsPreview = (date: string, page: number, signal?: AbortSignal) =>
  apiRequest<AbsenceSmsPreview>(
    `/school/sms/absences/preview/?date=${encodeURIComponent(date)}&page=${page}`,
    { signal },
  );

export const sendAbsenceSms = (date: string, studentIds: number[]) =>
  apiRequest<{ queued: number; skipped: number; queue_failed: number }>(
    "/school/sms/absences/send/",
    { method: "POST", body: { date, student_ids: studentIds } },
  );

export const getStudentSmsHistory = (studentId: number, page: number, signal?: AbortSignal) =>
  apiRequest<StudentSmsHistory>(
    `/school/sms/students/${studentId}/history/?page=${page}`,
    { signal },
  );
