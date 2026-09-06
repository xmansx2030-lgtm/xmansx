import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, CalendarDays, Database, HardDrive, ShieldCheck, Smartphone, UsersRound } from "lucide-react";

import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { getSchoolSubscription, type SubscriptionState, type Usage } from "@/features/platform/api";

const ACCESS_LABELS: Record<SubscriptionState["access_mode"], string> = {
  FULL: "وصول كامل",
  READ_ONLY: "قراءة فقط",
  BLOCKED: "الوصول موقوف",
};

const STATUS_LABELS: Record<string, string> = {
  TRIAL: "فترة تجريبية",
  ACTIVE: "نشط",
  GRACE_PERIOD: "فترة سماح",
  EXPIRED: "منتهي",
  SUSPENDED: "موقوف",
  CANCELLED: "ملغي",
};

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString("ar-SA") : "غير محدد";
}

function UsageRows({ usage }: { usage: Usage }) {
  const rows = [
    ["الطلاب", usage.students, UsersRound, "text-blue-700 bg-blue-50"],
    ["الموظفون", usage.staff, BadgeCheck, "text-emerald-700 bg-emerald-50"],
    ["الأجهزة", usage.devices, Smartphone, "text-violet-700 bg-violet-50"],
    ["التخزين", { ...usage.storage, used: usage.storage.used_gb, limit: usage.storage.limit_gb }, HardDrive, "text-amber-700 bg-amber-50"],
  ] as const;
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {rows.map(([label, row, Icon, tone]) => {
        const percentage = row.limit ? Math.min(100, Math.round((row.used / row.limit) * 100)) : null;
        return <section key={label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between gap-3"><p className="text-sm font-bold text-slate-700">{label}</p><span className={`grid size-9 place-items-center rounded-xl ${tone}`}><Icon aria-hidden size={18} /></span></div>
          <p className="mt-3 text-2xl font-black text-slate-950">
            {row.used} / {row.limit ?? "بلا حد"}
          </p>
          {percentage !== null && <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-label={`استخدام ${label}`} aria-valuenow={percentage} aria-valuemin={0} aria-valuemax={100}><span className={`block h-full rounded-full ${row.over_limit ? "bg-red-500" : row.near_limit ? "bg-amber-500" : "bg-teal-600"}`} style={{ width: `${percentage}%` }} /></div>}
          {row.over_limit && <p className="mt-1 text-sm font-semibold text-red-700">تجاوز الحد</p>}
          {!row.over_limit && row.near_limit && <p className="mt-1 text-sm font-semibold text-amber-700">قريب من الحد</p>}
          {!row.over_limit && !row.near_limit && <p className="mt-1 text-xs text-slate-500">ضمن حدود الباقة</p>}
        </section>;
      })}
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
    return <ErrorState error={query.error ?? new Error("تعذر تحميل بيانات الاشتراك.")} />;
  }
  const data = query.data;
  const subscription = data.subscription;
  const openAccessWithoutPlan = !subscription.has_subscription && subscription.access_mode === "FULL";
  const planLabel = subscription.plan?.name ?? (openAccessWithoutPlan ? "وصول تشغيلي بلا باقة" : "لا توجد باقة مفعلة");
  const statusLabel = openAccessWithoutPlan
    ? "غير مقيد بمدة"
    : subscription.status_label ?? (subscription.status ? STATUS_LABELS[subscription.status] : "لا يوجد اشتراك");

  return (
    <div className="space-y-5">
      <PageHeader
        icon={ShieldCheck}
        eyebrow="الحساب والحدود التشغيلية"
        title="اشتراك المدرسة"
        description="ملخص واضح لحالة الوصول، مدة الاشتراك، واستهلاك موارد المدرسة دون التأثير على بياناتها."
        tone="executive"
        badge={ACCESS_LABELS[subscription.access_mode]}
        meta={<><span>{planLabel}</span><span aria-hidden>•</span><span>{statusLabel}</span></>}
      />

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="mb-5 flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-teal-50 text-teal-700"><Database aria-hidden size={20} /></span><div><h2 className="font-black text-slate-950">تفاصيل الاشتراك</h2><p className="text-xs text-slate-500">المعلومات الحالية كما هي مسجلة للمدرسة</p></div></div>
        <div className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
          <Detail label="وضع الوصول" value={ACCESS_LABELS[subscription.access_mode]} icon={ShieldCheck} />
          <Detail label="الأيام المتبقية" value={subscription.days_remaining == null ? "غير محدد" : `${subscription.days_remaining} يومًا`} icon={CalendarDays} />
          <Detail label="تاريخ النهاية" value={formatDate(subscription.ends_at)} icon={CalendarDays} />
          <Detail label="نهاية التجربة" value={formatDate(subscription.trial_ends_at)} icon={CalendarDays} />
        </div>
        {subscription.access_mode !== "FULL" && (
          <p className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
            انتهى اشتراك المدرسة أو تم تقييده. البيانات محفوظة، وقد تكون العمليات الجديدة محدودة حتى تجديد الاشتراك.
          </p>
        )}
      </section>
      <div><h2 className="mb-1 text-lg font-black text-slate-950">استهلاك الباقة</h2><p className="mb-3 text-sm text-slate-500">متابعة الحدود قبل أن تؤثر على العمليات اليومية.</p></div>
      <UsageRows usage={data.usage} />
    </div>
  );
}

function Detail({ label, value, icon: Icon }: { label: string; value: string; icon: typeof CalendarDays }) {
  return <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4"><div className="flex items-center gap-2 text-xs font-bold text-slate-500"><Icon aria-hidden size={15} /> {label}</div><p className="mt-2 font-black text-slate-900">{value}</p></div>;
}
