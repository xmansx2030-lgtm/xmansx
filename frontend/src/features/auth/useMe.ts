import { useQuery, useQueryClient } from "@tanstack/react-query";

import { getMe, logout, switchActiveSchool } from "@/api/auth";
import { purgeSensitiveBrowserCaches } from "@/app/cacheSafety";
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
    await purgeSensitiveBrowserCaches();
    queryClient.setQueryData(ME_QUERY_KEY, me);
    return me;
  };
}

export function useLogout() {
  const queryClient = useQueryClient();

  return async (): Promise<void> => {
    // أوقف طلبات الجلسة القديمة قبل تدوير/حذف cookie الجلسة. وإلا قد تصل
    // استجابة متأخرة من طلب بدأ قبل الخروج وتمسح جلسة تسجيل دخول لاحقة.
    await queryClient.cancelQueries();
    try {
      await logout();
    } finally {
      queryClient.clear(); // حتى لو فشل الطلب: لا بيانات محلية بعد الخروج
      await purgeSensitiveBrowserCaches();
    }
  };
}
