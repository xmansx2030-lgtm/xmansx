import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BadgeCheck, CalendarDays, Check, Database, HardDrive, ShieldCheck, Smartphone, UsersRound } from "lucide-react";

import { ErrorState } from "@/components/ErrorState";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { useMe } from "@/features/auth/useMe";
import { getSchoolSubscription, type SubscriptionState, type Usage } from "@/features/platform/api";
import { getPublicPlans, type PublicPlan } from "@/features/public/api";
import type { SchoolType } from "@/types/auth";
import { formatPlanDuration } from "@/utils/planDuration";
import { studentPluralLabel } from "@/utils/roles";

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

const PLAN_LIMITS = [
  ["MAX_STUDENTS", "طالب"],
  ["MAX_STAFF", "موظف"],
  ["MAX_DEVICES", "جهاز حضور"],
  ["MAX_STORAGE_GB", "جيجابايت تخزين"],
] as const;

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString("ar-SA") : "غير محدد";
}

function planHighlights(plan: PublicPlan) {
  return PLAN_LIMITS.flatMap(([key, label]) => {
    if (!Object.prototype.hasOwnProperty.call(plan.entitlements, key)) return [];
    const value = plan.entitlements[key];
    if (value === null) return [`${label} بلا حد`];
    if (typeof value === "number") return [`حتى ${value.toLocaleString("ar-SA")} ${label}`];
    return [];
  });
}

function planRequestUrl(planName: string, schoolName: string) {
  const message = `السلام عليكم، أرغب في اختيار ${planName} لمدرسة ${schoolName} في منصة المواظبة XMANSX.`;
  return `https://wa.me/966537720207?text=${encodeURIComponent(message)}`;
}

function UsageRows({ usage, schoolType }: { usage: Usage; schoolType: SchoolType }) {
  const rows = [
    [studentPluralLabel(schoolType), usage.students, UsersRound, "text-blue-700 bg-blue-50"],
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
  const me = useMe();
  const schoolType = me.data?.active_school?.school_type ?? "BOYS";
  const schoolName = me.data?.active_school?.name ?? "مدرستي";
  const query = useQuery({
    queryKey: ["school", "subscription"],
    queryFn: ({ signal }) => getSchoolSubscription(signal),
  });
  const plans = useQuery({
    queryKey: ["public-plans"],
    queryFn: ({ signal }) => getPublicPlans(signal),
    staleTime: 5 * 60_000,
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
  const durationLabel = subscription.duration_value && subscription.duration_unit
    ? formatPlanDuration(subscription.duration_value, subscription.duration_unit)
    : "غير محددة";

  return (
    <div className="ds-page">
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
        <div className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-5">
          <Detail label="وضع الوصول" value={ACCESS_LABELS[subscription.access_mode]} icon={ShieldCheck} />
          <Detail label="مدة الباقة" value={durationLabel} icon={CalendarDays} />
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
      <UsageRows usage={data.usage} schoolType={schoolType} />

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6" aria-labelledby="available-plans-title">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <p className="text-xs font-black text-teal-700">مقارنة الباقات</p>
            <h2 id="available-plans-title" className="mt-1 text-xl font-black text-slate-950">اختر الباقة المناسبة لمدرستك</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">راجع المدة والسعر والحدود، ثم أرسل طلب اختيار الباقة إلى فريق الاشتراكات.</p>
          </div>
          <span className="w-fit rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">الباقة الحالية: {planLabel}</span>
        </div>

        {plans.isPending ? (
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label="جارٍ تحميل الباقات">
            {[0, 1, 2].map((item) => <div key={item} className="h-72 animate-pulse rounded-2xl bg-slate-100" />)}
          </div>
        ) : plans.isError ? (
          <p role="alert" className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">تعذر تحميل الباقات المتاحة الآن. أعد المحاولة لاحقًا أو تواصل مع فريق الاشتراكات.</p>
        ) : plans.data && plans.data.length > 0 ? (
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {plans.data.map((plan) => {
              const isCurrent = plan.code === subscription.plan?.code;
              const isFree = Number(plan.price_amount) === 0;
              const duration = formatPlanDuration(plan.duration_value, plan.duration_unit);
              const highlights = planHighlights(plan);
              return (
                <article key={plan.id} className={`flex flex-col rounded-2xl border p-5 ${isCurrent ? "border-teal-400 bg-teal-50/60 ring-2 ring-teal-100" : "border-slate-200 bg-white"}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div><p className="text-lg font-black text-slate-950">{plan.name}</p><p className="mt-1 text-sm font-bold text-teal-800">{isFree ? "مجانية" : `${Number(plan.price_amount).toLocaleString("ar-SA")} ${plan.currency}`}</p></div>
                    {isCurrent && <span className="shrink-0 rounded-full bg-teal-700 px-2.5 py-1 text-xs font-black text-white">باقتك الحالية</span>}
                  </div>
                  <p className="mt-3 text-xs font-bold text-slate-600">المدة: {duration}</p>
                  <p className="mt-3 min-h-12 text-sm leading-6 text-slate-600">{plan.description || "باقة تشغيل ومتابعة مدرسية متكاملة."}</p>
                  {highlights.length > 0 && <ul className="mt-4 flex-1 space-y-2 border-t border-slate-200/80 pt-4">{highlights.map((item) => <li key={item} className="flex items-center gap-2 text-sm text-slate-700"><Check aria-hidden size={15} className="text-teal-700" />{item}</li>)}</ul>}
                  {isCurrent ? (
                    <span className="mt-5 inline-flex min-h-11 items-center justify-center rounded-xl bg-teal-100 px-4 text-sm font-black text-teal-900">مفعلة حاليًا</span>
                  ) : (
                    <a href={planRequestUrl(plan.name, schoolName)} target="_blank" rel="noreferrer" className="mt-5 inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 text-sm font-black text-white hover:bg-teal-800">اطلب اختيار هذه الباقة <ArrowLeft aria-hidden size={16} /></a>
                  )}
                </article>
              );
            })}
          </div>
        ) : (
          <p className="mt-5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">لا توجد باقات عامة متاحة للطلب حاليًا.</p>
        )}
      </section>
    </div>
  );
}

function Detail({ label, value, icon: Icon }: { label: string; value: string; icon: typeof CalendarDays }) {
  return <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4"><div className="flex items-center gap-2 text-xs font-bold text-slate-500"><Icon aria-hidden size={15} /> {label}</div><p className="mt-2 font-black text-slate-900">{value}</p></div>;
}
