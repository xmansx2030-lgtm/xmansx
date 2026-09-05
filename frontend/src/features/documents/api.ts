/** الإجراءات الطلابية والمستندات المولدة (م12).
 *
 * الواجهة ترسل **نية** فقط: نوع المستند والطالب والمدى. كل بيانات اللقطة يبنيها
 * الخادم — لا `metric_value_at_issue` ولا `snapshot_data` ولا `template_version`
 * من العميل (البند 92).
 */

import { apiRequest } from "@/api/client";
import type { Paginated } from "@/features/warnings/api";

export type ActionType =
  | "PARENT_CONTACT"
  | "STUDENT_MEETING"
  | "PARENT_MEETING"
  | "COMMITMENT_TAKEN"
  | "WARNING_DELIVERED"
  | "ADMINISTRATIVE_NOTE"
  | "OTHER";

export const ACTION_TYPE_LABELS: Record<ActionType, string> = {
  PARENT_CONTACT: "التواصل مع ولي الأمر",
  STUDENT_MEETING: "مقابلة الطالب",
  PARENT_MEETING: "مقابلة ولي الأمر",
  COMMITMENT_TAKEN: "أخذ تعهد",
  WARNING_DELIVERED: "تسليم إنذار",
  ADMINISTRATIVE_NOTE: "ملاحظة إدارية",
  OTHER: "إجراء آخر",
};
export const ACTION_TYPES = Object.keys(ACTION_TYPE_LABELS) as ActionType[];

export type DocumentType =
  | "WARNING_LEVEL_1"
  | "WARNING_LEVEL_2"
  | "WARNING_LEVEL_3"
  | "ATTENDANCE_COMMITMENT"
  | "ABSENCE_DETAIL_REPORT"
  | "MORNING_LATE_DETAIL_REPORT"
  | "PERIOD_LATE_DETAIL_REPORT"
  | "STUDENT_ATTENDANCE_REPORT";

export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  WARNING_LEVEL_1: "الإنذار الأول",
  WARNING_LEVEL_2: "الإنذار الثاني",
  WARNING_LEVEL_3: "الإنذار الثالث",
  ATTENDANCE_COMMITMENT: "تعهد الالتزام بالحضور",
  ABSENCE_DETAIL_REPORT: "كشف تفصيلي للغياب",
  MORNING_LATE_DETAIL_REPORT: "كشف تفصيلي للتأخر الصباحي",
  PERIOD_LATE_DETAIL_REPORT: "كشف تفصيلي لتأخر الحصص",
  STUDENT_ATTENDANCE_REPORT: "تقرير مواظبة الطالب",
};

/** المستندات التي تحتاج مدى تواريخ من المستخدم (بقيتها من لقطة الإنذار). */
export const RANGE_DOCUMENT_TYPES: DocumentType[] = [
  "ATTENDANCE_COMMITMENT",
  "ABSENCE_DETAIL_REPORT",
  "MORNING_LATE_DETAIL_REPORT",
  "PERIOD_LATE_DETAIL_REPORT",
  "STUDENT_ATTENDANCE_REPORT",
];

export const WARNING_LEVEL_DOCUMENT: Record<"LEVEL_1" | "LEVEL_2" | "LEVEL_3", DocumentType> = {
  LEVEL_1: "WARNING_LEVEL_1",
  LEVEL_2: "WARNING_LEVEL_2",
  LEVEL_3: "WARNING_LEVEL_3",
};

export type DocumentStatus = "PENDING" | "READY" | "FAILED" | "VOIDED";

export interface ActionRow {
  id: number;
  student_id: number;
  action_type: ActionType;
  action_type_label: string;
  status: "COMPLETED" | "CANCELLED";
  status_label: string;
  warning_id: number | null;
  warning_label: string | null;
  performed_at: string;
  performed_by_name: string | null;
  notes: string;
  cancelled_at: string | null;
  cancelled_by_name: string | null;
  cancellation_reason: string;
}

export interface DocumentRow {
  id: number;
  student_id: number;
  document_type: DocumentType;
  document_type_label: string;
  status: DocumentStatus;
  status_label: string;
  template: string;
  warning_id: number | null;
  action_id: number | null;
  generated_at: string | null;
  generated_by_name: string | null;
  size_bytes: number;
  checksum: string;
  error_code: string;
  can_download: boolean;
}

export interface DocumentDetail extends DocumentRow {
  snapshot?: Record<string, unknown>;
}

export interface DocumentPreview {
  document_type: DocumentType;
  document_type_label: string;
  template: string;
  already_exists: boolean;
  snapshot: Record<string, unknown>;
}

export interface GeneratePayload {
  student_id: number;
  document_type: DocumentType;
  warning_id?: number;
  from_date?: string;
  to_date?: string;
  create_action?: boolean;
  notes?: string;
}

// توليد PDF لتقرير طويل يستغرق ثوانٍ (قياس: ~250ms لكل صفحة) — مهلة العميل الافتراضية
// 15 ثانية غير كافية، فترفع لهذا المسار وحده.
const GENERATE_TIMEOUT_MS = 60_000;

export const getStudentActions = (studentId: number, signal?: AbortSignal) =>
  apiRequest<Paginated<ActionRow>>(`/student-actions/?student=${studentId}`, { signal });

export const createStudentAction = (payload: {
  student_id: number;
  action_type: ActionType;
  warning_id?: number | null;
  notes?: string;
}) => apiRequest<ActionRow>("/student-actions/", { method: "POST", body: payload });

export const cancelStudentAction = (actionId: number, reason: string) =>
  apiRequest<ActionRow>(`/student-actions/${actionId}/cancel/`, {
    method: "POST",
    body: { reason },
  });

export const getStudentDocuments = (studentId: number, signal?: AbortSignal) =>
  apiRequest<Paginated<DocumentRow>>(`/documents/?student=${studentId}`, { signal });

export const previewDocument = (payload: Omit<GeneratePayload, "create_action" | "notes">) =>
  apiRequest<DocumentPreview>("/documents/preview/", { method: "POST", body: payload });

export const generateDocument = (payload: GeneratePayload) =>
  apiRequest<DocumentRow>("/documents/generate/", {
    method: "POST",
    body: payload,
    timeoutMs: GENERATE_TIMEOUT_MS,
  });

export const getDocumentDetail = (documentId: number, signal?: AbortSignal) =>
  apiRequest<DocumentDetail>(`/documents/${documentId}/`, { signal });

export const retryDocument = (documentId: number) =>
  apiRequest<DocumentRow>(`/documents/${documentId}/retry/`, {
    method: "POST",
    timeoutMs: GENERATE_TIMEOUT_MS,
  });

export const voidDocument = (documentId: number, reason: string) =>
  apiRequest<DocumentRow>(`/documents/${documentId}/void/`, {
    method: "POST",
    body: { reason },
  });

/** التنزيل عبر endpoint مصادق — لا رابط تخزين عام (البندان 55-57). */
export const documentDownloadUrl = (documentId: number) =>
  `/api/v1/documents/${documentId}/download/`;

/** عرض PDF داخل المتصفح لتمكين الطباعة مباشرة، مع بقاء المصادقة والصلاحيات. */
export const documentPrintUrl = (documentId: number) =>
  `/api/v1/documents/${documentId}/download/?inline=1`;
