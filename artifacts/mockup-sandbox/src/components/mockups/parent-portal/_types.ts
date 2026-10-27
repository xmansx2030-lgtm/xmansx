export type RelationStatus =
  | "PENDING"
  | "ACTIVE"
  | "SUSPENDED_CONTACT_REVIEW"
  | "REJECTED"
  | "REVOKED"
  | "UNAVAILABLE";
export type RequestStatus =
  "PENDING" | "NEEDS_INFO" | "APPROVED" | "REJECTED" | "CANCELLED";
export interface ParentDay {
  date: string;
  absence_status: "FULL" | "PARTIAL" | "NONE" | "UNDETERMINED";
  completeness_status: string;
  expected_periods: number;
  submitted_periods: number;
  present_periods: number;
  absent_periods: number;
  excused_absent_periods: number;
  unexcused_absent_periods: number;
  updated_at: string | null;
}
export interface Child {
  relation_id: number;
  school: { id: number; name: string };
  student: {
    id: number;
    full_name: string;
    grade_name: string | null;
    section_name: string | null;
    department?: string;
  } | null;
  status: RelationStatus;
  today: ParentDay | null;
  new_notifications?: number;
  required_actions?: number;
}
