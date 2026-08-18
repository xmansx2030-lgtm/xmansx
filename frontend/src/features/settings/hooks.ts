import { useQuery, useQueryClient } from "@tanstack/react-query";

import { schoolScopedKey, useMe } from "@/features/auth/useMe";
import {
  getSchedules,
  getSettings,
  getWeekDays,
  getYears,
} from "@/features/settings/api";

/** كل مفاتيح الإعدادات tenant-aware — تتضمن معرف المدرسة النشطة (منع تسرب cache). */
export function useActiveSchoolId(): number {
  const me = useMe();
  return me.data?.active_school?.id ?? 0;
}

export function useSettingsQuery() {
  const schoolId = useActiveSchoolId();
  return useQuery({
    queryKey: schoolScopedKey(schoolId, "settings"),
    queryFn: ({ signal }) => getSettings(signal),
    enabled: schoolId > 0,
  });
}

export function useYearsQuery() {
  const schoolId = useActiveSchoolId();
  return useQuery({
    queryKey: schoolScopedKey(schoolId, "academic-years"),
    queryFn: ({ signal }) => getYears(signal),
    enabled: schoolId > 0,
  });
}

export function useSchedulesQuery() {
  const schoolId = useActiveSchoolId();
  return useQuery({
    queryKey: schoolScopedKey(schoolId, "bell-schedules"),
    queryFn: ({ signal }) => getSchedules(signal),
    enabled: schoolId > 0,
  });
}

export function useWeekDaysQuery() {
  const schoolId = useActiveSchoolId();
  return useQuery({
    queryKey: schoolScopedKey(schoolId, "week-days"),
    queryFn: ({ signal }) => getWeekDays(signal),
    enabled: schoolId > 0,
  });
}

export function useInvalidateSchoolData() {
  const queryClient = useQueryClient();
  const schoolId = useActiveSchoolId();
  return (...parts: string[]) =>
    queryClient.invalidateQueries({ queryKey: schoolScopedKey(schoolId, ...parts) });
}
