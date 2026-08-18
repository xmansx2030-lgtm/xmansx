import { apiRequest, getCookie } from "@/api/client";

// ---- الأنواع ----

export interface SchoolSettingsPayload {
  school: { id: number; name: string; slug: string };
  ministry_school_number: string;
  education_stage: "ELEMENTARY" | "MIDDLE" | "SECONDARY" | "MULTI_STAGE";
  city: string;
  official_principal_name: string;
  timezone: string;
  logo_url: string | null;
  attendance_edit_window_minutes: number;
  unprepared_period_alert_minutes: number;
  staff: { managers: string[]; vice_principals: string[]; counselors: string[] };
}

export interface Semester {
  id: number;
  name: string;
  sequence: number;
  start_date: string;
  end_date: string;
  status: "UPCOMING" | "ACTIVE" | "CLOSED";
}

export interface AcademicYear {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  status: "UPCOMING" | "ACTIVE" | "CLOSED" | "ARCHIVED";
  semesters: Semester[];
}

export interface BellPeriod {
  id?: number;
  sequence: number;
  name: string;
  start_time: string;
  end_time: string;
  is_attendance_period: boolean;
}

export interface BellSchedule {
  id: number;
  name: string;
  status: "ACTIVE" | "INACTIVE" | "ARCHIVED";
  valid_from: string | null;
  valid_to: string | null;
  periods: BellPeriod[];
}

export interface WeekDay {
  weekday: number;
  is_school_day: boolean;
  bell_schedule_id: number | null;
  bell_schedule_name: string | null;
}

// ---- الإعدادات ----

export const getSettings = (signal?: AbortSignal) =>
  apiRequest<SchoolSettingsPayload>("/school/settings/", { signal });

export const patchSettings = (data: Partial<Record<string, unknown>>) =>
  apiRequest<SchoolSettingsPayload>("/school/settings/", { method: "PATCH", body: data });

// ---- الأعوام والفصول ----

export const getYears = (signal?: AbortSignal) =>
  apiRequest<AcademicYear[]>("/school/academic-years/", { signal });

export const createYear = (data: { name: string; start_date: string; end_date: string }) =>
  apiRequest<AcademicYear>("/school/academic-years/", { method: "POST", body: data });

export const yearAction = (yearId: number, action: "activate" | "close" | "archive") =>
  apiRequest<AcademicYear>(`/school/academic-years/${yearId}/${action}/`, { method: "POST" });

export const createSemester = (
  yearId: number,
  data: { name: string; sequence: number; start_date: string; end_date: string },
) =>
  apiRequest<Semester>(`/school/academic-years/${yearId}/semesters/`, {
    method: "POST",
    body: data,
  });

export const activateSemester = (semesterId: number) =>
  apiRequest<Semester>(`/school/semesters/${semesterId}/activate/`, { method: "POST" });

// ---- جداول الحصص وأيام الأسبوع ----

export const getSchedules = (signal?: AbortSignal) =>
  apiRequest<BellSchedule[]>("/school/bell-schedules/", { signal });

export const createSchedule = (data: { name: string }) =>
  apiRequest<BellSchedule>("/school/bell-schedules/", { method: "POST", body: data });

export const archiveSchedule = (scheduleId: number) =>
  apiRequest<BellSchedule>(`/school/bell-schedules/${scheduleId}/archive/`, { method: "POST" });

export const replacePeriods = (scheduleId: number, periods: Omit<BellPeriod, "id">[]) =>
  apiRequest<BellSchedule>(`/school/bell-schedules/${scheduleId}/periods/`, {
    method: "PUT",
    body: { periods },
  });

export const getWeekDays = (signal?: AbortSignal) =>
  apiRequest<{ days: WeekDay[] }>("/school/week-days/", { signal });

export const putWeekDays = (
  days: { weekday: number; is_school_day: boolean; bell_schedule_id: number | null }[],
) => apiRequest<{ days: WeekDay[] }>("/school/week-days/", { method: "PUT", body: { days } });

export async function uploadLogo(file: File): Promise<SchoolSettingsPayload> {
  const formData = new FormData();
  formData.append("logo", file);
  const response = await fetch("/api/v1/school/settings/logo/", {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRFToken": getCookie("csrftoken") ?? "" },
    body: formData,
  });
  if (!response.ok) {
    const body = (await response.json()) as { message?: string };
    throw new Error(body.message ?? "تعذر رفع الشعار.");
  }
  return (await response.json()) as SchoolSettingsPayload;
}

export const WEEKDAY_LABELS = [
  "الأحد",
  "الاثنين",
  "الثلاثاء",
  "الأربعاء",
  "الخميس",
  "الجمعة",
  "السبت",
] as const;

export const STAGE_LABELS: Record<SchoolSettingsPayload["education_stage"], string> = {
  ELEMENTARY: "ابتدائي",
  MIDDLE: "متوسط",
  SECONDARY: "ثانوي",
  MULTI_STAGE: "متعدد المراحل",
};
