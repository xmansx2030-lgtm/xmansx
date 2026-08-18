import { useQuery } from "@tanstack/react-query";

import { getHealth } from "@/api/health";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";

/** صفحة مؤقتة للأساس: تعرض حالة الاتصال بالخادم عبر طبقة API + TanStack Query.
 *  تستبدل بشاشة الدخول في المرحلة 2. */
export function HomePage() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => getHealth(signal),
  });

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="mb-2 text-xl font-bold">الأساس التقني جاهز</h2>
      <p className="mb-4 text-slate-600">
        هذه صفحة مؤقتة للمرحلة الأولى. شاشة تسجيل الدخول تأتي في المرحلة الثانية.
      </p>
      <div className="flex items-center gap-2 text-sm" data-testid="backend-status">
        <span className="text-slate-500">حالة الخادم:</span>
        {healthQuery.isPending && <Spinner label="جارٍ الفحص..." />}
        {healthQuery.isError && <ErrorState error={healthQuery.error} />}
        {healthQuery.isSuccess && (
          <span className="inline-flex items-center gap-1 font-medium text-emerald-700">
            <span className="size-2 rounded-full bg-emerald-500" aria-hidden />
            متصل
          </span>
        )}
      </div>
    </section>
  );
}
