import { apiRequest } from "@/api/client";

export interface GateRelease {
  released_at: string;
  released_by_name: string | null;
}

export interface GateStudentLeave {
  id: number;
  student: {
    id: number;
    full_name: string;
    student_number: string | null;
  };
  leave_date: string;
  leave_time: string;
  grade_name: string;
  section_name: string;
  recorded_by_name: string | null;
  recipient_name: string;
  recipient_relationship: string;
  recipient_id_last4: string;
  gate_release: GateRelease | null;
}

export interface GateStudentLeaveList {
  date: string;
  summary: { total: number; pending: number; released: number };
  results: GateStudentLeave[];
}

export function getGateStudentLeaves(search: string, signal?: AbortSignal) {
  const query = new URLSearchParams();
  if (search.trim()) query.set("search", search.trim());
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<GateStudentLeaveList>(`/gate/student-leaves/${suffix}`, { signal });
}

export function confirmGateRelease(leaveId: number) {
  return apiRequest<GateStudentLeave>(`/gate/student-leaves/${leaveId}/release/`, {
    method: "POST",
  });
}
