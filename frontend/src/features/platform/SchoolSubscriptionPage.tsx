import { useQuery } from "@tanstack/react-query";

import { Spinner } from "@/components/Spinner";
import { getSchoolSubscription, type Usage } from "@/features/platform/api";

function UsageRows({ usage }: { usage: Usage }) {
  const rows = [
    ["الطلاب", usage.students],
    ["الموظفون", usage.staff],
    ["الأجهزة", usage.devices],
    ["التخزين", { ...usage.storage, used: usage.storage.used_gb, limit: usage.storage.limit_gb }],
  ] as const;
  return (
    <div className="grid gap-3 md:grid-cols-4">
      {rows.map(([label, row]) => (
        <div key={label} className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm text-slate-500">{label}</p>
          <p className="mt-1 text-xl font-bold text-slate-900">
            {row.used} / {row.limit ?? "بلا حد"}
          </p>
          {row.over_limit && <p className="mt-1 text-sm font-semibold text-red-700">تجاوز الحد</p>}
          {!row.over_limit && row.near_limit && <p className="mt-1 text-sm font-semibold text-amber-700">قريب من الحد</p>}
        </div>
      ))}
    </div>
  );
}

export function SchoolSubscriptionPage() {
  const query = useQuery({
    queryKey: ["school", "subscription"],
    queryFn: ({ signal }) => getSchoolSubscription(signal),
  });

  if (query.isPending) return <Spinner label="جارٍ تحميل الاشتراك..." />;
  if (query.isError || !query.data) {
    return (
      <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
        تعذر تحميل بيانات الاشتراك.
      </p>
    );
  }
  const data = query.data;
  const subscription = data.subscription;

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h1 className="text-xl font-bold text-slate-900">اشتراك المدرسة</h1>
        <p className="mt-2 text-slate-600">
          {subscription.plan?.name ?? "لا توجد باقة"} · {subscription.status ?? "لا يوجد اشتراك"}
        </p>
        <div className="mt-4 grid gap-3 text-sm text-slate-600 md:grid-cols-4">
          <p>وضع الوصول: <b>{subscription.access_mode}</b></p>
          <p>الأيام المتبقية: <b>{subscription.days_remaining ?? "-"}</b></p>
          <p>تاريخ النهاية: <b>{subscription.ends_at ? new Date(subscription.ends_at).toLocaleDateString("ar-SA") : "-"}</b></p>
          <p>نهاية التجربة: <b>{subscription.trial_ends_at ? new Date(subscription.trial_ends_at).toLocaleDateString("ar-SA") : "-"}</b></p>
        </div>
        {subscription.access_mode !== "FULL" && (
          <p className="mt-4 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            انتهى اشتراك المدرسة أو تم تقييده. البيانات محفوظة، وقد تكون العمليات الجديدة محدودة حتى تجديد الاشتراك.
          </p>
        )}
      </section>
      <UsageRows usage={data.usage} />
    </div>
  );
}
