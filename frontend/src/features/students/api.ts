import { apiRequest, getCookie } from "@/api/client";

const IMPORT_COMMIT_TIMEOUT_MS = 120_000;

// ---- الأنواع ----

export interface StudentRow {
  id: number;
  full_name: string;
  national_id_masked: string;
  student_number: string | null;
  status: string;
  guardian_name: string;
  grade: { id: number; name: string } | null;
  section: { id: number; name: string } | null;
}

export interface AttendanceProfile {
  student: StudentRow;
  period: { from: string; to: string };
  attendance: {
    full_absence_days: number;
    partial_absence_days: number;
    undetermined_days: number;
    absent_periods: number;
    // م10 — التصنيف الإداري (الإجماليات أعلاه تبقى كما هي)
    excused_absent_periods: number;
    unexcused_absent_periods: number;
    excused_full_absence_days: number;
    unexcused_full_absence_days: number;
    mixed_full_absence_days: number;
  };
  morning_attendance: {
    status: "AVAILABLE" | "NOT_AVAILABLE";
    morning_late_occurrences?: number;
    morning_late_minutes?: number;
  };
}

export interface MorningAttendanceHistory {
  date: string;
  arrival_time: string;
  status: string;
  raw_late_minutes: number;
  counted_late_minutes: number;
  source: string;
  grade_name: string | null;
  section_name: string | null;
}

export interface AttendanceDay {
  date: string;
  absence_status: "FULL" | "PARTIAL" | "NONE" | "UNDETERMINED";
  absence_status_label: string;
  section: { id: number; name: string; grade_name: string } | null;
  absent_periods: number;
  excused_absent_periods: number;
  unexcused_absent_periods: number;
}

export interface AttendancePeriod {
  date: string;
  sequence: number;
  period: { sequence: number; name: string; start_time?: string; end_time?: string };
  section: { name: string; grade_name: string };
}

export interface AttendanceDayDetail extends AttendanceDay {
  periods: Array<{
    sequence: number;
    name: string;
    status: "ABSENT" | "PRESENT" | "NOT_RECORDED";
    status_label: string;
    /** م10 — للغياب فقط: true بعذر معتمد، false بدون عذر، null لغير الغياب. */
    excused: boolean | null;
  }>;
}

export interface AttendanceChange {
  date: string;
  sequence: number;
  period: { sequence: number; name: string };
  previous_status: string;
  new_status: string;
  previous_status_label: string;
  new_status_label: string;
  reason: string | null;
  actor: string | null;
  changed_at: string;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface GradeItem {
  id: number;
  name: string;
  code: string;
  sequence: number;
  is_active: boolean;
}

export interface SectionItem {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  grade: { id: number; name: string; is_active: boolean };
}

export interface ManualStudentInput {
  full_name: string;
  national_id: string;
  student_number?: string;
  guardian_name?: string;
  guardian_mobile?: string;
  section_id: number;
}

export interface StudentUpdateInput {
  full_name?: string;
  national_id?: string;
  student_number?: string;
  guardian_name?: string;
  guardian_mobile?: string;
  section_id?: number;
}

export type MappingField =
  | "national_id"
  | "full_name"
  | "grade"
  | "section"
  | "student_number"
  | "guardian_name"
  | "guardian_mobile";

export interface ImportJob {
  id: number;
  status:
    | "UPLOADED"
    | "PROCESSING"
    | "READY_FOR_REVIEW"
    | "IMPORTING"
    | "COMPLETED"
    | "FAILED"
    | "CANCELLED";
  original_filename: string;
  headers: string[];
  header_row?: number;
  import_format?: "TABULAR" | "NOOR_OFFICIAL_MULTI_SHEET";
  source_sheet_count?: number;
  detected_rows?: number;
  column_mapping: Partial<Record<MappingField, number>>;
  suggested_mapping: Partial<Record<MappingField, number | null>> | null;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  summary: {
    new?: number;
    unchanged?: number;
    updated?: number;
    section_changed?: number;
    grade_changed?: number;
    errors?: number;
    duplicates?: number;
    auto_resolved_duplicates?: number;
    section_candidates?: Array<{
      grade_code: string;
      grade_name: string;
      section_code: string;
      section_name: string;
    }>;
    missing_from_file?: number;
    missing_names?: { student_id: number; name: string }[];
    will_create_grades?: string[];
    will_create_sections?: string[];
    created?: number;
    enrollment_changes?: number;
    student_capacity?: {
      used: number;
      adding: number;
      projected: number;
      limit: number | null;
      over_limit: boolean;
    };
  };
  error_code: string;
  error_message?: string;
}

export interface PreviewRow {
  row_number: number;
  status: string;
  data: {
    full_name?: string;
    grade_name?: string;
    section_name?: string;
    national_id_masked?: string;
    changes?: Record<string, { from?: string; to?: string }>;
  };
  error_codes: string[];
  error_message: string;
}

export interface ImportRowCorrection {
  national_id?: string;
  student_number?: string;
  full_name?: string;
  section_id?: number;
  section_code?: string;
}

// ---- الطلاب ----

export function getStudents(
  params: {
    page?: number;
    search?: string;
    national_id?: string;
    grade?: number | "";
    section?: number | "";
    status?: string;
  },
  signal?: AbortSignal,
): Promise<Paginated<StudentRow>> {
  const query = new URLSearchParams();
  if (params.page) query.set("page", String(params.page));
  if (params.search) query.set("search", params.search);
  if (params.national_id) query.set("national_id", params.national_id);
  if (params.grade) query.set("grade", String(params.grade));
  if (params.section) query.set("section", String(params.section));
  if (params.status) query.set("status", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<Paginated<StudentRow>>(`/students/${suffix}`, { signal });
}

export const createStudent = (input: ManualStudentInput) =>
  apiRequest<StudentRow>("/students/", { method: "POST", body: input });

export const updateStudent = (id: number, input: StudentUpdateInput) =>
  apiRequest<StudentRow>(`/students/${id}/`, { method: "PATCH", body: input });

function profileQuery(params: { fromDate: string; toDate: string }): string {
  return `?from_date=${encodeURIComponent(params.fromDate)}&to_date=${encodeURIComponent(params.toDate)}`;
}

export const getAttendanceProfile = (
  studentId: number,
  params: { fromDate: string; toDate: string },
  signal?: AbortSignal,
) => apiRequest<AttendanceProfile>(
  `/students/${studentId}/attendance-profile/${profileQuery(params)}`,
  { signal },
);

export const getAttendanceDays = (
  studentId: number,
  params: { fromDate: string; toDate: string; page?: number },
  signal?: AbortSignal,
) => apiRequest<Paginated<AttendanceDay>>(
  `/students/${studentId}/attendance-days/${profileQuery(params)}${params.page ? `&page=${params.page}` : ""}`,
  { signal },
);

export const getAttendanceDayDetail = (
  studentId: number,
  date: string,
  signal?: AbortSignal,
) => apiRequest<AttendanceDayDetail>(`/students/${studentId}/attendance-days/${date}/`, { signal });

export const getMorningAttendance = (
  studentId: number,
  params: { fromDate: string; toDate: string },
  signal?: AbortSignal,
) => apiRequest<MorningAttendanceHistory[]>(
  `/students/${studentId}/morning-attendance/${profileQuery(params)}`,
  { signal },
);

export const getAttendancePeriodAbsences = (
  studentId: number,
  params: { fromDate: string; toDate: string; page?: number },
  signal?: AbortSignal,
) => apiRequest<Paginated<AttendancePeriod>>(
  `/students/${studentId}/attendance-period-absences/${profileQuery(params)}${params.page ? `&page=${params.page}` : ""}`,
  { signal },
);

export const getAttendanceChanges = (
  studentId: number,
  params: { fromDate: string; toDate: string; page?: number },
  signal?: AbortSignal,
) => apiRequest<Paginated<AttendanceChange>>(
  `/students/${studentId}/attendance-changes/${profileQuery(params)}${params.page ? `&page=${params.page}` : ""}`,
  { signal },
);

export const getGrades = (signal?: AbortSignal, includeInactive = false) =>
  apiRequest<GradeItem[]>(`/grades/${includeInactive ? "?include_inactive=1" : ""}`, { signal });

export const getSections = (signal?: AbortSignal, includeInactive = false) =>
  apiRequest<SectionItem[]>(`/sections/${includeInactive ? "?include_inactive=1" : ""}`, { signal });

export const createGrade = (body: { name: string; code: string; sequence: number }) =>
  apiRequest<GradeItem>("/grades/", { method: "POST", body });

export const createSection = (body: { grade_id: number; name: string; code: string }) =>
  apiRequest<SectionItem>("/sections/", { method: "POST", body });

export const updateGrade = (
  id: number,
  body: Partial<Pick<GradeItem, "name" | "code" | "sequence" | "is_active">>,
) => apiRequest<GradeItem>(`/grades/${id}/`, { method: "PATCH", body });

export const deleteGrade = (id: number) =>
  apiRequest<void>(`/grades/${id}/`, { method: "DELETE" });

export const updateSection = (
  id: number,
  body: Partial<Pick<SectionItem, "name" | "code" | "is_active">> & { grade_id?: number },
) => apiRequest<SectionItem>(`/sections/${id}/`, { method: "PATCH", body });

export const deleteSection = (id: number) =>
  apiRequest<void>(`/sections/${id}/`, { method: "DELETE" });

// ---- الاستيراد ----

export async function uploadImportFile(file: File): Promise<ImportJob> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/api/v1/student-imports/", {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
    body: formData,
  });
  const body = (await response.json()) as ImportJob & { code?: string; message?: string };
  if (!response.ok) {
    throw new Error(body.message ?? "تعذر رفع الملف.");
  }
  return body;
}

export const getImportJob = (jobId: number, signal?: AbortSignal) =>
  apiRequest<ImportJob>(`/student-imports/${jobId}/`, { signal });

export const processImportJob = (
  jobId: number,
  mapping: Partial<Record<MappingField, number>>,
) =>
  apiRequest<ImportJob>(`/student-imports/${jobId}/process/`, {
    method: "POST",
    body: { mapping },
  });

export const getImportPreview = (jobId: number, category: string, page: number) =>
  apiRequest<Paginated<PreviewRow>>(
    `/student-imports/${jobId}/preview/?category=${encodeURIComponent(category)}&page=${page}`,
  );

export const correctImportRow = (
  jobId: number,
  rowNumber: number,
  body: ImportRowCorrection,
) => apiRequest<ImportJob>(`/student-imports/${jobId}/rows/${rowNumber}/`, {
  method: "PATCH",
  body,
});

export const commitImportJob = (jobId: number) =>
  apiRequest<ImportJob>(`/student-imports/${jobId}/commit/`, {
    method: "POST",
    timeoutMs: IMPORT_COMMIT_TIMEOUT_MS,
  });

export const cancelImportJob = (jobId: number) =>
  apiRequest<ImportJob>(`/student-imports/${jobId}/cancel/`, { method: "POST" });

export const MAPPING_LABELS: Record<MappingField, string> = {
  national_id: "رقم الهوية",
  full_name: "اسم الطالب",
  grade: "الصف",
  section: "الفصل",
  student_number: "رقم الطالب",
  guardian_name: "اسم ولي الأمر",
  guardian_mobile: "جوال ولي الأمر",
};

// ---- دورة الحياة والحذف النهائي (المرحلة 4.1) ----

export interface InactiveStudent {
  id: number;
  full_name: string;
  national_id_masked: string;
  status: string;
  exit_date: string | null;
  exit_reason: string;
  grade: { name: string } | null;
  section: { name: string } | null;
}

export interface PurgePreview {
  confirmation_token: string;
  summary: Record<string, number> & { students: number; database_records: number };
  expires_in_seconds: number;
}

export interface PurgeJob {
  id: number;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "PARTIALLY_FAILED" | "FAILED";
  reason: string;
  total_students: number;
  processed_students: number;
  deleted_students: number;
  failed_students: number;
  db_records_deleted: number;
  storage_objects_deleted: number;
  storage_objects_failed: number;
}

export function getInactiveStudents(
  params: {
    page?: number;
    status?: string;
    missing_last_import?: boolean;
    search?: string;
  },
  signal?: AbortSignal,
): Promise<Paginated<InactiveStudent>> {
  const query = new URLSearchParams();
  if (params.page) query.set("page", String(params.page));
  if (params.status) query.set("status", params.status);
  if (params.missing_last_import) query.set("missing_last_import", "1");
  if (params.search) query.set("search", params.search);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<Paginated<InactiveStudent>>(`/students/inactive/${suffix}`, { signal });
}

export const setStudentStatus = (
  studentId: number,
  status: string,
  exitReason = "",
) =>
  apiRequest<{ id: number; status: string }>(`/students/${studentId}/status/`, {
    method: "POST",
    body: { status, exit_reason: exitReason },
  });

export const bulkSetStatus = (studentIds: number[], status: string, exitReason = "") =>
  apiRequest<{ updated: number; status: string }>("/students/bulk-status/", {
    method: "POST",
    body: { student_ids: studentIds, status, exit_reason: exitReason },
  });

export const purgePreview = (studentIds: number[]) =>
  apiRequest<PurgePreview>("/student-purges/preview/", {
    method: "POST",
    body: { student_ids: studentIds },
  });

export const createPurge = (confirmationToken: string, reason = "") =>
  apiRequest<PurgeJob>("/student-purges/", {
    method: "POST",
    body: { confirmation_token: confirmationToken, reason },
  });

export const getPurgeJob = (jobId: number, signal?: AbortSignal) =>
  apiRequest<PurgeJob>(`/student-purges/${jobId}/`, { signal });

export const LIFECYCLE_STATUS_LABELS: Record<string, string> = {
  ACTIVE: "نشط",
  GRADUATED: "متخرج",
  TRANSFERRED: "منتقل",
  WITHDRAWN: "منسحب",
  INACTIVE: "غير نشط",
  ARCHIVED: "مؤرشف",
};

export const CATEGORY_LABELS: Record<string, string> = {
  "": "الكل",
  NEW: "جدد",
  EXISTING_UNCHANGED: "بلا تغيير",
  EXISTING_UPDATED: "تحديث",
  SECTION_CHANGED: "انتقال فصل",
  GRADE_CHANGED: "تغير صف",
  ERROR: "أخطاء",
  DUPLICATE_IN_FILE: "تكرارات",
  AUTO_RESOLVED_DUPLICATE: "تكرارات عولجت تلقائيًا",
};
