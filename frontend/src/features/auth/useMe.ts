import { useQuery, useQueryClient } from "@tanstack/react-query";

import { getMe, logout, switchActiveSchool } from "@/api/auth";
import type { Me } from "@/types/auth";

export const ME_QUERY_KEY = ["me"] as const;

/** مفتاح موحد للبيانات المدرسية المستقبلية — يتضمن معرف المدرسة النشطة دائمًا
 *  حتى لا يختلط cache مدرستين (نمط إلزامي للمراحل القادمة). */
export function schoolScopedKey(activeSchoolId: number, ...parts: unknown[]) {
  return ["school", activeSchoolId, ...parts] as const;
}

export function useMe() {
  return useQuery<Me>({
    queryKey: ME_QUERY_KEY,
    queryFn: ({ signal }) => getMe(signal),
    staleTime: 60_000,
  });
}

export function useSwitchSchool() {
  const queryClient = useQueryClient();

  return async (schoolId: number): Promise<Me> => {
    const me = await switchActiveSchool(schoolId);
    // نقطة أمنية: إزالة كل الاستعلامات غير me — لا يبقى أي أثر لبيانات المدرسة السابقة
    await queryClient.cancelQueries();
    queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    queryClient.setQueryData(ME_QUERY_KEY, me);
    return me;
  };
}

export function useLogout() {
  const queryClient = useQueryClient();

  return async (): Promise<void> => {
    try {
      await logout();
    } finally {
      queryClient.clear(); // حتى لو فشل الطلب: لا بيانات محلية بعد الخروج
    }
  };
}
