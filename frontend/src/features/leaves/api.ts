import { apiRequest } from "@/api/client";
import type { Paginated, StudentRow } from "@/features/students/api";

export type StudentLeaveStatus = "ACTIVE" | "CANCELLED";

export interface StudentLeaveRow {
  id: number;
  student: Pick<StudentRow, "id" | "full_name" | "student_number" | "national_id_masked">;
  leave_date: string;
  leave_time: string;
  weekday_label: string;
  reason: string;
  recipient_name: string;
  recipient_relationship: string;
  recipient_id_last4: string;
  grade_name: string;
  section_name: string;
  status: StudentLeaveStatus;
  status_label: string;
  recorded_by_name: string | null;
  created_at: string;
  cancelled_by_name: string | null;
  cancelled_at: string | null;
  cancellation_reason: string;
  gate_release: { released_at: string; released_by_name: string | null } | null;
}

export interface StudentLeavePage extends Paginated<StudentLeaveRow> {
  summary: { total: number; active: number; cancelled: number };
}

export interface CreateStudentLeaveInput {
  student_id: number;
  leave_date: string;
  leave_time: string;
  reason: string;
  recipient_name?: string;
  recipient_relationship?: string;
  recipient_id_last4?: string;
}

export function getStudentLeaves(
  params: {
    page?: number;
    date?: string;
    search?: string;
    status?: StudentLeaveStatus | "";
    student?: number;
  },
  signal?: AbortSignal,
) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", String(params.page));
  if (params.date) query.set("date", params.date);
  if (params.search) query.set("search", params.search);
  if (params.status) query.set("status", params.status);
  if (params.student) query.set("student", String(params.student));
  return apiRequest<StudentLeavePage>(`/student-leaves/?${query.toString()}`, { signal });
}

export const createStudentLeave = (input: CreateStudentLeaveInput) =>
  apiRequest<StudentLeaveRow>("/student-leaves/", { method: "POST", body: input });

export const cancelStudentLeave = (id: number, reason: string) =>
  apiRequest<StudentLeaveRow>(`/student-leaves/${id}/cancel/`, {
    method: "POST",
    body: { reason },
  });
