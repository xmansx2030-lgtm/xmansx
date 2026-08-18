import { apiRequest, getCookie } from "@/api/client";

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
}

export interface SectionItem {
  id: number;
  name: string;
  code: string;
  grade: { id: number; name: string };
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
    missing_from_file?: number;
    missing_names?: { student_id: number; name: string }[];
    will_create_grades?: string[];
    will_create_sections?: string[];
    created?: number;
    enrollment_changes?: number;
  };
  error_code: string;
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

// ---- الطلاب ----

export function getStudents(
  params: {
    page?: number;
    search?: string;
    national_id?: string;
    grade?: number | "";
    section?: number | "";
  },
  signal?: AbortSignal,
): Promise<Paginated<StudentRow>> {
  const query = new URLSearchParams();
  if (params.page) query.set("page", String(params.page));
  if (params.search) query.set("search", params.search);
  if (params.national_id) query.set("national_id", params.national_id);
  if (params.grade) query.set("grade", String(params.grade));
  if (params.section) query.set("section", String(params.section));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<Paginated<StudentRow>>(`/students/${suffix}`, { signal });
}

export const getGrades = (signal?: AbortSignal) =>
  apiRequest<GradeItem[]>("/grades/", { signal });

export const getSections = (signal?: AbortSignal) =>
  apiRequest<SectionItem[]>("/sections/", { signal });

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

export const commitImportJob = (jobId: number) =>
  apiRequest<ImportJob>(`/student-imports/${jobId}/commit/`, { method: "POST" });

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

export const CATEGORY_LABELS: Record<string, string> = {
  "": "الكل",
  NEW: "جدد",
  EXISTING_UNCHANGED: "بلا تغيير",
  EXISTING_UPDATED: "تحديث",
  SECTION_CHANGED: "انتقال فصل",
  GRADE_CHANGED: "تغير صف",
  ERROR: "أخطاء",
  DUPLICATE_IN_FILE: "تكرارات",
};
