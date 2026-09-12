import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  BarChart3,
  Building2,
  CalendarClock,
  ChevronLeft,
  CircleDollarSign,
  Database,
  LogOut,
  PackageCheck,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Trash2,
  UserRoundCog,
  UsersRound,
} from "lucide-react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { Spinner } from "@/components/Spinner";
import { useLogout, useMe } from "@/features/auth/useMe";
import {
  addSchoolManager,
  createPlan,
  createPlatformSchool,
  deletePlatformSchool,
  disablePlan,
  getPlans,
  getPlatformOverview,
  getPlatformSchools,
  getPlanChangePreview,
  getSchoolDetail,
  getSubscriptionEvents,
  getSubscriptionHistory,
  runSubscriptionAction,
  runSchoolManagerAction,
  updatePlatformSchool,
  updatePlan,
  updateSchoolManager,
  type ManagerCredentialResponse,
  type Overview,
  type Plan,
  type PlanInput,
  type SchoolDetail,
  type SchoolManagerAccount,
  type SchoolRow,
  type Usage,
} from "@/features/platform/api";
import type { SchoolType } from "@/types/auth";
import type { PlatformCapability } from "@/types/auth";
import { PlatformAccountPanel, PlatformTeamPanel } from "@/features/platform/PlatformTeamPanels";

const LIMIT_KEYS = ["MAX_STUDENTS", "MAX_STAFF", "MAX_DEVICES", "MAX_STORAGE_GB"] as const;
const LIMIT_FORM_KEYS = {
  MAX_STUDENTS: "max_students",
  MAX_STAFF: "max_staff",
  MAX_DEVICES: "max_devices",
  MAX_STORAGE_GB: "max_storage_gb",
} as const;
const FEATURE_KEYS = [
  "ATTENDANCE",
  "BIOMETRIC_DEVICES",
  "ROSTER_SYNC",
  "EXCUSES",
  "WARNINGS",
  "DOCUMENTS",
  "REFERRALS",
  "COUNSELING",
  "EXECUTIVE_DASHBOARD",
] as const;

const STATUS_LABELS: Record<string, string> = {
  NO_SUBSCRIPTION: "بدون اشتراك",
  TRIAL: "تجريبي",
  ACTIVE: "نشط",
  GRACE_PERIOD: "مهلة سماح",
  EXPIRED: "منتهي",
  SUSPENDED: "موقوف",
  CANCELLED: "ملغي",
};
const ENTITLEMENT_LABELS: Record<string, string> = {
  MAX_STUDENTS: "الحد الأقصى للطلاب",
  MAX_STAFF: "الحد الأقصى للموظفين",
  MAX_DEVICES: "الحد الأقصى للأجهزة",
  MAX_STORAGE_GB: "التخزين (GB)",
  ATTENDANCE: "التحضير",
  BIOMETRIC_DEVICES: "أجهزة البصمة",
  ROSTER_SYNC: "مزامنة القوائم",
  EXCUSES: "الأعذار",
  WARNINGS: "الإنذارات",
  DOCUMENTS: "المستندات",
  REFERRALS: "الإحالات",
  COUNSELING: "الإرشاد الطلابي",
  EXECUTIVE_DASHBOARD: "لوحة المؤشرات التنفيذية",
};

const statusLabel = (status: string | null | undefined) =>
  STATUS_LABELS[status ?? "NO_SUBSCRIPTION"] ?? status ?? STATUS_LABELS.NO_SUBSCRIPTION;

function statusClass(status: string | null | undefined) {
  if (status === "ACTIVE" || status === "TRIAL") return "bg-emerald-50 text-emerald-700";
  if (status === "GRACE_PERIOD") return "bg-amber-50 text-amber-700";
  if (status === "SUSPENDED" || status === "CANCELLED") return "bg-red-50 text-red-700";
  return "bg-slate-100 text-slate-700";
}

type PlatformTab = "dashboard" | "schools" | "plans" | "team" | "account";
type SubscriptionActionName =
  | "start-trial"
  | "extend-trial"
  | "activate"
  | "change-plan"
  | "extend"
  | "suspend"
  | "reactivate"
  | "cancel";

const SUBSCRIPTION_ACTION_LABELS: Record<SubscriptionActionName, string> = {
  "start-trial": "بدء فترة تجريبية",
  "extend-trial": "تمديد الفترة التجريبية",
  activate: "تفعيل اشتراك",
  "change-plan": "تغيير الباقة",
  extend: "تمديد الاشتراك",
  suspend: "إيقاف الاشتراك",
  reactivate: "إعادة تفعيل الاشتراك",
  cancel: "إلغاء الاشتراك",
};

function subscriptionActionsFor(status: string | null): SubscriptionActionName[] {
  if (status === "TRIAL") return ["activate", "extend-trial", "change-plan"];
  if (status === "ACTIVE" || status === "GRACE_PERIOD") return ["extend", "change-plan"];
  if (status === "SUSPENDED") return ["reactivate"];
  if (status === "EXPIRED") return ["activate", "start-trial", "extend"];
  return ["activate", "start-trial"];
}

function defaultSubscriptionAction(status: string | null): SubscriptionActionName {
  if (status === "TRIAL") return "activate";
  if (status === "ACTIVE" || status === "GRACE_PERIOD") return "extend";
  if (status === "SUSPENDED") return "reactivate";
  return "activate";
}

const PLATFORM_TABS = [
  {
    id: "dashboard" as const,
    label: "لوحة المؤشرات",
    description: "الصحة العامة والتنبيهات",
    icon: BarChart3,
    capability: "DASHBOARD_VIEW" as PlatformCapability,
  },
  {
    id: "schools" as const,
    label: "المدارس",
    description: "الحسابات والاشتراكات",
    icon: Building2,
    capability: "SCHOOLS_VIEW" as PlatformCapability,
  },
  {
    id: "plans" as const,
    label: "الباقات",
    description: "الحدود والمزايا",
    icon: PackageCheck,
    capability: "PLANS_VIEW" as PlatformCapability,
  },
  {
    id: "team" as const,
    label: "فريق المنصة",
    description: "الموظفون والصلاحيات",
    icon: UsersRound,
    capability: "TEAM_VIEW" as PlatformCapability,
  },
  {
    id: "account" as const,
    label: "حسابي",
    description: "الملف الشخصي والأمان",
    icon: UserRoundCog,
    capability: null,
  },
] satisfies { id: PlatformTab; label: string; description: string; icon: typeof BarChart3; capability: PlatformCapability | null }[];

const numberFormat = new Intl.NumberFormat("ar-SA");

function DashboardMetric({
  label,
  value,
  hint,
  icon: Icon,
  tone = "teal",
}: {
  label: string;
  value: number;
  hint: string;
  icon: typeof BarChart3;
  tone?: "teal" | "blue" | "amber" | "slate";
}) {
  const tones = {
    teal: "bg-teal-50 text-teal-700 ring-teal-100",
    blue: "bg-blue-50 text-blue-700 ring-blue-100",
    amber: "bg-amber-50 text-amber-700 ring-amber-100",
    slate: "bg-slate-100 text-slate-700 ring-slate-200",
  } as const;

  return (
    <article className="group relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-md">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-500">{label}</p>
          <p className="mt-2 text-3xl font-black tracking-tight text-slate-950">{value}</p>
          <p className="mt-1 text-xs leading-5 text-slate-500">{hint}</p>
        </div>
        <span className={`grid size-11 shrink-0 place-items-center rounded-2xl ring-1 ${tones[tone]}`}>
          <Icon aria-hidden size={21} strokeWidth={2.2} />
        </span>
      </div>
      <span className="absolute inset-x-0 bottom-0 h-0.5 origin-right scale-x-0 bg-gradient-to-l from-teal-500 to-blue-500 transition-transform duration-300 group-hover:scale-x-100" />
    </article>
  );
}

function DashboardPanel({ overview, onOpenSchools }: { overview: Overview; onOpenSchools: () => void }) {
  const active = overview.subscriptions.active ?? 0;
  const trial = overview.subscriptions.trial ?? 0;
  const grace = overview.subscriptions.grace ?? 0;
  const expired = overview.subscriptions.expired ?? 0;
  const suspended = overview.subscriptions.suspended ?? 0;
  const expiring = overview.expiring_soon ?? [];
  const statusTotal = active + trial + grace + expired + suspended;
  const coverage = overview.schools_total > 0 ? Math.min(100, Math.round(((active + trial) / overview.schools_total) * 100)) : 0;
  const statusRows = [
    { label: "نشطة", value: active, color: "bg-emerald-500", text: "text-emerald-700" },
    { label: "تجريبية", value: trial, color: "bg-blue-500", text: "text-blue-700" },
    { label: "مهلة سماح", value: grace, color: "bg-amber-500", text: "text-amber-700" },
    { label: "منتهية", value: expired, color: "bg-rose-500", text: "text-rose-700" },
    { label: "موقوفة", value: suspended, color: "bg-slate-500", text: "text-slate-700" },
  ];

  return (
    <div className="space-y-5" data-testid="platform-dashboard">
      <section className="relative overflow-hidden rounded-3xl bg-slate-950 px-5 py-6 text-white shadow-xl shadow-slate-950/10 sm:px-7 sm:py-7">
        <div className="absolute -start-20 -top-24 size-64 rounded-full bg-teal-500/20 blur-3xl" />
        <div className="absolute -bottom-28 end-10 size-64 rounded-full bg-blue-500/15 blur-3xl" />
        <div className="relative grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <div className="mb-4 flex items-center gap-2 text-sm font-bold text-teal-300">
              <Sparkles aria-hidden size={17} />
              <span>ملخص المنصة الآن</span>
            </div>
            <h2 className="max-w-2xl text-2xl font-black leading-tight sm:text-3xl">نظرة تنفيذية لاتخاذ القرار بسرعة</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">متابعة حالة المدارس والاشتراكات والسعة التشغيلية من شاشة واحدة، دون الوصول إلى بيانات الطلاب.</p>
          </div>
          <div className="flex items-center gap-4 rounded-2xl border border-white/10 bg-white/7 px-5 py-4 backdrop-blur-sm">
            <div className="relative grid size-16 place-items-center rounded-full bg-[conic-gradient(#2dd4bf_var(--coverage),#334155_0)]" style={{ "--coverage": `${coverage * 3.6}deg` } as CSSProperties}>
              <span className="grid size-12 place-items-center rounded-full bg-slate-950 text-sm font-black">{coverage}%</span>
            </div>
            <div>
              <p className="font-bold">تغطية فعّالة</p>
              <p className="mt-1 text-xs text-slate-400">نشطة أو ضمن الفترة التجريبية</p>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="المؤشرات الرئيسية">
        <DashboardMetric label="إجمالي المدارس" value={overview.schools_total ?? 0} hint="كل المدارس المسجلة بالمنصة" icon={Building2} />
        <DashboardMetric label="الاشتراكات النشطة" value={active} hint="وصول تشغيلي كامل حاليًا" icon={ShieldCheck} tone="blue" />
        <DashboardMetric label="تنتهي قريبًا" value={expiring.length} hint="تحتاج متابعة قبل الانقطاع" icon={CalendarClock} tone="amber" />
        <DashboardMetric label="الاشتراكات المسجلة" value={statusTotal} hint="اشتراكات موزعة على الحالات" icon={CircleDollarSign} tone="slate" />
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <article className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm sm:p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-black text-slate-950">توزيع حالات الاشتراك</h3>
              <p className="mt-1 text-xs text-slate-500">قراءة سريعة لمحفظة المدارس الحالية</p>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600">{numberFormat.format(statusTotal)} اشتراك</span>
          </div>
          <div className="mt-6 space-y-4">
            {statusRows.map((row) => {
              const percentage = statusTotal > 0 ? Math.round((row.value / statusTotal) * 100) : 0;
              return (
                <div key={row.label}>
                  <div className="mb-1.5 flex items-center justify-between gap-4 text-sm">
                    <span className="font-semibold text-slate-700">{row.label}</span>
                    <span className={`font-black ${row.text}`}>{numberFormat.format(row.value)} <span className="text-xs font-medium text-slate-400">({percentage}%)</span></span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                    <div className={`h-full rounded-full transition-all duration-700 ${row.color}`} style={{ width: `${percentage}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </article>

        <article className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm sm:p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-black text-slate-950">السعة التشغيلية</h3>
              <p className="mt-1 text-xs text-slate-500">إجماليات الاستخدام النشط عبر المنصة</p>
            </div>
            <Database aria-hidden className="text-slate-400" size={21} />
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
            {[
              { label: "الطلاب النشطون", value: overview.usage_totals?.active_students ?? 0, icon: UsersRound, tone: "bg-teal-50 text-teal-700" },
              { label: "الموظفون", value: overview.usage_totals?.active_staff ?? 0, icon: ServerCog, tone: "bg-blue-50 text-blue-700" },
              { label: "الأجهزة", value: overview.usage_totals?.active_devices ?? 0, icon: Smartphone, tone: "bg-violet-50 text-violet-700" },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <div key={item.label} className="flex items-center gap-3 rounded-xl border border-slate-100 bg-slate-50/70 p-3.5">
                  <span className={`grid size-10 place-items-center rounded-xl ${item.tone}`}><Icon aria-hidden size={19} /></span>
                  <div><p className="text-xs font-semibold text-slate-500">{item.label}</p><p className="text-xl font-black text-slate-950">{item.value}</p></div>
                </div>
              );
            })}
          </div>
        </article>
      </section>

      <section className="rounded-2xl border border-slate-200/80 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 sm:px-6">
          <div>
            <h3 className="flex items-center gap-2 text-base font-black text-slate-950"><AlertTriangle aria-hidden className="text-amber-500" size={19} />متابعة انتهاء الاشتراكات</h3>
            <p className="mt-1 text-xs text-slate-500">المدارس التي يقترب موعد انتهاء اشتراكها</p>
          </div>
          <button type="button" onClick={onOpenSchools} className="inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-bold text-teal-700 transition hover:bg-teal-50">
            إدارة المدارس <ChevronLeft aria-hidden size={16} />
          </button>
        </div>
        {expiring.length > 0 ? (
          <div className="divide-y divide-slate-100">
            {expiring.slice(0, 5).map((school) => (
              <div key={school.school_id} className="grid gap-2 px-5 py-4 sm:grid-cols-[1fr_auto_auto] sm:items-center sm:px-6">
                <div><p className="font-bold text-slate-900">{school.school_name}</p><p className="mt-0.5 text-xs text-slate-500">باقة {school.plan}</p></div>
                <p className="text-xs text-slate-500">تنتهي {formatDate(school.ends_at)}</p>
                <span className="w-fit rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-700">متبقي {numberFormat.format(school.days_remaining)} يوم</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center px-5 py-9 text-center">
            <span className="grid size-11 place-items-center rounded-full bg-emerald-50 text-emerald-700"><ShieldCheck aria-hidden size={21} /></span>
            <p className="mt-3 font-bold text-slate-800">لا توجد اشتراكات قريبة من الانتهاء</p>
            <p className="mt-1 text-xs text-slate-500">لا توجد متابعة عاجلة مطلوبة حاليًا.</p>
          </div>
        )}
      </section>
    </div>
  );
}

function ErrorLine({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof ApiError ? error.message : "تعذر تنفيذ الطلب.";
  return <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{message}</p>;
}

function UsageGrid({ usage }: { usage: Usage }) {
  const rows = [
    ["الطلاب", usage.students],
    ["الموظفون", usage.staff],
    ["الأجهزة", usage.devices],
    ["التخزين", { ...usage.storage, used: usage.storage.used_gb, limit: usage.storage.limit_gb }],
  ] as const;
  return (
    <div className="grid grid-cols-2 gap-3">
      {rows.map(([label, row]) => (
        <div key={label} className="rounded-lg border border-slate-200 bg-white p-3">
          <p className="text-xs text-slate-500">{label}</p>
          <p className="mt-1 text-lg font-bold text-slate-900">
            {row.used} / {row.limit ?? "بلا حد"}
          </p>
          {row.over_limit && <p className="mt-1 text-xs font-semibold text-red-700">تجاوز الحد</p>}
          {!row.over_limit && row.near_limit && <p className="mt-1 text-xs font-semibold text-amber-700">قريب من الحد</p>}
        </div>
      ))}
    </div>
  );
}

const formatDate = (value: string | null | undefined) =>
  value ? new Intl.DateTimeFormat("ar-SA", { dateStyle: "medium" }).format(new Date(value)) : "—";

function canonicalMobileForCredentials(value: string): string {
  const latin = [...value.trim()].map((char) => {
    const index = "٠١٢٣٤٥٦٧٨٩".indexOf(char);
    return index === -1 ? char : String(index);
  }).join("");
  const compact = latin.replace(/[\s\-().]/g, "");
  const digits = compact.startsWith("+")
    ? compact.slice(1)
    : compact.startsWith("00")
      ? compact.slice(2)
      : compact;
  const national = digits.startsWith("966")
    ? digits.slice(3)
    : digits.startsWith("05")
      ? digits.slice(1)
      : digits;
  return /^5\d{8}$/.test(national) ? `+966${national}` : value;
}

function CredentialNotice({
  mobile,
  password,
  managerLabel,
  onClose,
}: {
  mobile: string;
  password: string | null;
  managerLabel: "المدير" | "المديرة";
  onClose: () => void;
}) {
  const canonicalMobile = canonicalMobileForCredentials(mobile);
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950" role="status">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-bold">بيانات الدخول</p>
          <p className="mt-1">رقم الجوال: <b dir="ltr">{canonicalMobile}</b></p>
          {password ? (
            <>
              <p>كلمة المرور المؤقتة: <b dir="ltr">{password}</b></p>
              <p className="mt-1 text-xs">تظهر مرة واحدة، وسيُطلب من {managerLabel} تغييرها بعد الدخول.</p>
            </>
          ) : (
            <p className="mt-1 text-xs">الحساب موجود مسبقًا ويستخدم كلمة مروره الحالية.</p>
          )}
        </div>
        <button type="button" className="text-xs font-bold text-amber-900" onClick={onClose}>إخفاء</button>
      </div>
      {password && (
        <Button
          type="button"
          variant="secondary"
          className="mt-2 px-3 py-1.5"
          onClick={() => void navigator.clipboard.writeText(`رقم الجوال: ${canonicalMobile}\nكلمة المرور المؤقتة: ${password}`)}
        >
          نسخ بيانات الدخول
        </Button>
      )}
    </div>
  );
}

function ManagerAccountCard({
  schoolId,
  manager,
  schoolType,
  canManage,
}: {
  schoolId: number;
  manager: SchoolManagerAccount;
  schoolType: SchoolType;
  canManage: boolean;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(manager.name);
  const [mobile, setMobile] = useState(manager.mobile);
  const [confirmation, setConfirmation] = useState<"reset-password" | "suspend" | null>(null);
  const [sharedImpactAcknowledged, setSharedImpactAcknowledged] = useState(false);
  const [credentials, setCredentials] = useState<ManagerCredentialResponse | null>(null);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["platform", "school", schoolId] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "schools"] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "overview"] }),
    ]);
  };
  const save = useMutation({
    mutationFn: () => updateSchoolManager(schoolId, manager.membership_id, {
      name,
      mobile,
      confirm_shared_account_impact: sharedImpactAcknowledged,
    }),
    onSuccess: async () => {
      setSharedImpactAcknowledged(false);
      await refresh();
    },
  });
  const accountAction = useMutation({
    mutationFn: (action: "reset-password" | "suspend" | "reactivate") =>
      runSchoolManagerAction(
        schoolId,
        manager.membership_id,
        action,
        action === "reset-password" && manager.shared_with_other_schools,
      ),
    onSuccess: async (result) => {
      if ("temporary_password" in result) setCredentials(result);
      setConfirmation(null);
      await refresh();
    },
  });
  const active = manager.membership_status === "ACTIVE";
  const managerLabel = schoolType === "GIRLS" ? "المديرة" : "المدير";

  return (
    <article className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-bold text-slate-900">{manager.name}</p>
          <p className="text-xs text-slate-500">
            {active ? "عضوية فعالة" : "عضوية موقوفة"} · آخر دخول {formatDate(manager.last_login)}
          </p>
        </div>
        <span className={`rounded px-2 py-1 text-xs ${manager.must_change_password ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
          {manager.must_change_password ? "بانتظار تغيير كلمة المرور" : "بيانات الدخول مفعلة"}
        </span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="text-xs font-semibold text-slate-600">
          اسم {managerLabel}
          <input disabled={!canManage} aria-label={`اسم ${managerLabel} ${manager.membership_id}`} className="mt-1 w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm disabled:bg-slate-100" value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label className="text-xs font-semibold text-slate-600">
          رقم الجوال للدخول
          <input disabled={!canManage} aria-label={`جوال ${managerLabel} ${manager.membership_id}`} dir="ltr" className="mt-1 w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm text-left disabled:bg-slate-100" value={mobile} onChange={(event) => setMobile(event.target.value)} />
        </label>
      </div>
      {manager.shared_with_other_schools && (
        <label className="mt-2 flex items-start gap-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
          <input
            type="checkbox"
            checked={sharedImpactAcknowledged}
            onChange={(event) => setSharedImpactAcknowledged(event.target.checked)}
          />
          أؤكد أن تعديل الاسم أو الجوال سيؤثر في الحساب نفسه لدى جميع المدارس المرتبطة.
        </label>
      )}
      {canManage && <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" className="px-3 py-1.5" disabled={save.isPending || (manager.shared_with_other_schools && !sharedImpactAcknowledged)} onClick={() => save.mutate()}>حفظ بيانات الحساب</Button>
        <Button type="button" variant="secondary" className="px-3 py-1.5" disabled={accountAction.isPending} onClick={() => setConfirmation("reset-password")}>إعادة ضبط كلمة المرور</Button>
        {active ? (
          <Button type="button" variant="danger" className="px-3 py-1.5" disabled={accountAction.isPending} onClick={() => setConfirmation("suspend")}>إيقاف {managerLabel}</Button>
        ) : (
          <Button type="button" variant="secondary" className="px-3 py-1.5" disabled={accountAction.isPending} onClick={() => accountAction.mutate("reactivate")}>إعادة تفعيل {managerLabel}</Button>
        )}
      </div>}
      {confirmation && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          <p>{confirmation === "reset-password" ? `سيتم إبطال كلمة المرور الحالية وإصدار كلمة مؤقتة جديدة${manager.shared_with_other_schools ? "، وسيؤثر ذلك في الدخول إلى جميع المدارس المرتبطة بهذا الحساب." : "."}` : `سيتوقف وصول ${managerLabel} إلى المدرسة. لا يمكن إيقاف الحساب الإداري الوحيد.`}</p>
          <div className="mt-2 flex gap-2">
            <Button type="button" variant="danger" className="px-3 py-1.5" onClick={() => accountAction.mutate(confirmation)}>تأكيد</Button>
            <Button type="button" variant="secondary" className="px-3 py-1.5" onClick={() => setConfirmation(null)}>تراجع</Button>
          </div>
        </div>
      )}
      <div className="mt-2"><ErrorLine error={save.error ?? accountAction.error} /></div>
      {credentials && <div className="mt-3"><CredentialNotice mobile={credentials.manager.mobile} password={credentials.temporary_password} managerLabel={managerLabel} onClose={() => setCredentials(null)} /></div>}
    </article>
  );
}

function SchoolAccountManagement({ detail, canManageSchool, canManageAccounts }: { detail: SchoolDetail; canManageSchool: boolean; canManageAccounts: boolean }) {
  const queryClient = useQueryClient();
  const [schoolName, setSchoolName] = useState(detail.name);
  const [schoolStatus, setSchoolStatus] = useState(detail.school_status);
  const [schoolType, setSchoolType] = useState<SchoolType>(detail.school_type ?? "BOYS");
  const [newManager, setNewManager] = useState({ name: "", mobile: "" });
  const [credentials, setCredentials] = useState<ManagerCredentialResponse | null>(null);
  const managerNoun = schoolType === "GIRLS" ? "مديرة" : "مدير";

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["platform", "school", detail.id] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "schools"] }),
      queryClient.invalidateQueries({ queryKey: ["platform", "overview"] }),
    ]);
  };
  const saveSchool = useMutation({
    mutationFn: () => updatePlatformSchool(detail.id, { name: schoolName, school_status: schoolStatus, school_type: schoolType }),
    onSuccess: refresh,
  });
  const addManager = useMutation({
    mutationFn: () => addSchoolManager(detail.id, newManager),
    onSuccess: async (result) => {
      setCredentials(result);
      setNewManager({ name: "", mobile: "" });
      await refresh();
    },
  });

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <div>
        <h3 className="font-bold text-slate-900">بيانات المدرسة والدخول</h3>
        <p className="text-xs text-slate-500">المعرف: {detail.slug} · أضيفت {formatDate(detail.created_at)}</p>
      </div>
      {canManageSchool && <><div className="grid gap-2 sm:grid-cols-[1fr_130px_150px]">
        <label className="text-xs font-semibold text-slate-600">
          اسم المدرسة
          <input aria-label="اسم المدرسة المسجلة" className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm" value={schoolName} onChange={(event) => setSchoolName(event.target.value)} />
        </label>
        <label className="text-xs font-semibold text-slate-600">
          نوع المدرسة
          <select aria-label="نوع المدرسة المسجلة" className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm" value={schoolType} onChange={(event) => setSchoolType(event.target.value as SchoolType)}>
            <option value="BOYS">بنين</option>
            <option value="GIRLS">بنات</option>
          </select>
        </label>
        <label className="text-xs font-semibold text-slate-600">
          حالة المدرسة
          <select aria-label="حالة المدرسة التشغيلية" className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm" value={schoolStatus} onChange={(event) => setSchoolStatus(event.target.value)}>
            <option value="ACTIVE">نشطة</option>
            <option value="SUSPENDED">موقوفة</option>
            <option value="ARCHIVED">مؤرشفة</option>
          </select>
        </label>
      </div>
      <p className="text-xs text-slate-500">إيقاف المدرسة يمنع جميع حساباتها من الدخول حتى إعادة تفعيلها.</p>
      <Button type="button" className="px-3 py-1.5" disabled={saveSchool.isPending} onClick={() => saveSchool.mutate()}>حفظ بيانات المدرسة</Button>
      <ErrorLine error={saveSchool.error} /></>}

      <div className="border-t border-slate-200 pt-3">
        <h4 className="font-bold text-slate-900">حساب {schoolType === "GIRLS" ? "مديرة المدرسة" : "مدير المدرسة"}</h4>
        <p className="mb-3 text-xs text-slate-500">لكل مدرسة حساب مدير واحد فقط، ويمكن تحديث بياناته أو إعادة ضبط كلمة مروره من هنا.</p>
        <div className="space-y-3">
          {(detail.managers ?? []).map((manager) => <ManagerAccountCard key={`${manager.membership_id}:${manager.name}:${manager.mobile}`} schoolId={detail.id} manager={manager} schoolType={schoolType} canManage={canManageAccounts} />)}
          {(detail.managers ?? []).length === 0 && <p className="rounded bg-amber-50 p-3 text-sm text-amber-800">لا يوجد {managerNoun} مرتبط بهذه المدرسة.</p>}
          {(detail.managers ?? []).length > 1 && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm font-bold text-red-800">يوجد تعارض قديم: ترتبط بهذه المدرسة عدة حسابات مدير. أوقف المعالجة الآلية وراجع الحسابات القائمة بعناية؛ لن يسمح النظام بإضافة أي مدير جديد.</p>}
        </div>
      </div>

      {canManageAccounts && ((detail.managers ?? []).length === 0 ? (
        <form className="border-t border-slate-200 pt-3" onSubmit={(event) => { event.preventDefault(); addManager.mutate(); }}>
          <h4 className="mb-1 font-bold text-slate-900">تعيين {managerNoun} المدرسة</h4>
          <p className="mb-3 text-xs text-slate-500">يظهر هذا الإجراء فقط لاسترداد مدرسة لا يوجد لها مدير. بعد التعيين لن يقبل النظام مديرًا ثانيًا.</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input aria-label={`اسم ${schoolType === "GIRLS" ? "المديرة" : "المدير"} الجديد`} className="rounded border border-slate-300 px-3 py-2 text-sm" placeholder={`اسم ${schoolType === "GIRLS" ? "المديرة" : "المدير"}`} value={newManager.name} onChange={(event) => setNewManager({ ...newManager, name: event.target.value })} />
            <input aria-label={`جوال ${schoolType === "GIRLS" ? "المديرة" : "المدير"} الجديد`} dir="ltr" className="rounded border border-slate-300 px-3 py-2 text-left text-sm" placeholder="05XXXXXXXX" value={newManager.mobile} onChange={(event) => setNewManager({ ...newManager, mobile: event.target.value })} />
          </div>
          <Button type="submit" className="mt-2 px-3 py-1.5" disabled={addManager.isPending}>تعيين {managerNoun}</Button>
          <div className="mt-2"><ErrorLine error={addManager.error} /></div>
        </form>
      ) : (
        <div className="border-t border-slate-200 pt-3">
          <p className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs leading-5 text-emerald-900">
            <ShieldCheck aria-hidden size={16} className="mt-0.5 shrink-0" />
            المدرسة محمية بحساب {schoolType === "GIRLS" ? "مديرة واحدة" : "مدير واحد"}. استخدم بطاقة الحساب أعلاه لتحديث بيانات {schoolType === "GIRLS" ? "المديرة الحالية" : "المدير الحالي"} بدل إضافة حساب آخر.
          </p>
        </div>
      ))}
      {credentials && <CredentialNotice mobile={credentials.manager.mobile} password={credentials.temporary_password} managerLabel={schoolType === "GIRLS" ? "المديرة" : "المدير"} onClose={() => setCredentials(null)} />}
    </div>
  );
}

function PlanForm({ plans, canManage }: { plans: Plan[]; canManage: boolean }) {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<number | null>(null);
  const editing = plans.find((plan) => plan.id === editingId);
  const [form, setForm] = useState({
    code: "",
    name_ar: "",
    price_amount: "0",
    trial_days_default: 30,
    max_students: 1000,
    max_staff: 100,
    max_devices: 5,
    max_storage_gb: 10,
  });
  const [features, setFeatures] = useState<Record<string, boolean>>(
    Object.fromEntries(FEATURE_KEYS.map((key) => [key, true])),
  );

  const save = useMutation({
    mutationFn: (body: PlanInput) =>
      editingId ? updatePlan(editingId, body) : createPlan(body),
    onSuccess: async () => {
      setEditingId(null);
      setForm({ ...form, code: "", name_ar: "" });
      await queryClient.invalidateQueries({ queryKey: ["platform", "plans"] });
    },
  });

  function load(plan: Plan) {
    setEditingId(plan.id);
    setForm({
      code: plan.code,
      name_ar: plan.name_ar,
      price_amount: plan.price_amount,
      trial_days_default: plan.trial_days_default,
      max_students: Number(plan.entitlements.MAX_STUDENTS ?? 1000),
      max_staff: Number(plan.entitlements.MAX_STAFF ?? 100),
      max_devices: Number(plan.entitlements.MAX_DEVICES ?? 5),
      max_storage_gb: Number(plan.entitlements.MAX_STORAGE_GB ?? 10),
    });
    setFeatures(
      Object.fromEntries(FEATURE_KEYS.map((key) => [key, Boolean(plan.entitlements[key] ?? true)])),
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const entitlements: Record<string, number | boolean> = {
      MAX_STUDENTS: form.max_students,
      MAX_STAFF: form.max_staff,
      MAX_DEVICES: form.max_devices,
      MAX_STORAGE_GB: form.max_storage_gb,
      ...features,
    };
    save.mutate({
      ...(editing ? {} : { code: form.code }),
      name_ar: form.name_ar,
      price_amount: form.price_amount,
      currency: "SAR",
      billing_period: "ANNUAL",
      trial_days_default: form.trial_days_default,
      entitlements,
    });
  }

  return (
    <section className="space-y-4">
      {!canManage && <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm font-bold text-blue-800">عرض فقط — لا يتضمن دورك إنشاء الباقات أو تعديلها.</div>}
      {canManage && <form onSubmit={submit} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-4">
        <div className="md:col-span-4"><h2 className="font-black text-slate-950">{editing ? `تعديل باقة ${editing.name_ar}` : "إنشاء باقة جديدة"}</h2><p className="mt-1 text-xs text-slate-500">حدد السعر والحدود ثم اختر المزايا المتاحة للمدرسة.</p></div>
        <label className="text-sm font-medium text-slate-700">رمز الباقة<input required className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5" placeholder="مثال: PRO" value={form.code} disabled={Boolean(editing)} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label>
        <label className="text-sm font-medium text-slate-700">اسم الباقة<input required className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5" placeholder="اسم الباقة" value={form.name_ar} onChange={(e) => setForm({ ...form, name_ar: e.target.value })} /></label>
        <label className="text-sm font-medium text-slate-700">السعر السنوي (ر.س)<input required min={0} className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5" placeholder="السعر" value={form.price_amount} onChange={(e) => setForm({ ...form, price_amount: e.target.value })} /></label>
        <label className="text-sm font-medium text-slate-700">أيام التجربة الافتراضية<input required min={0} className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5" type="number" placeholder="أيام التجربة" value={form.trial_days_default} onChange={(e) => setForm({ ...form, trial_days_default: Number(e.target.value) })} /></label>
        {LIMIT_KEYS.map((key) => (
          <label key={key} className="text-sm text-slate-600">
            {ENTITLEMENT_LABELS[key]}
            <input className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5" min={0} type="number" value={form[LIMIT_FORM_KEYS[key]]} onChange={(e) => setForm({ ...form, [LIMIT_FORM_KEYS[key]]: Number(e.target.value) })} />
          </label>
        ))}
        <fieldset className="grid gap-2 rounded-2xl bg-slate-50 p-3 md:col-span-4 md:grid-cols-3">
          <legend className="px-1 text-sm font-black text-slate-800">المزايا المتاحة</legend>
          {FEATURE_KEYS.map((key) => (
            <label key={key} className="flex min-h-10 items-center gap-2 rounded-xl bg-white px-3 text-sm text-slate-700">
              <input className="size-4" type="checkbox" checked={features[key]} onChange={(e) => setFeatures({ ...features, [key]: e.target.checked })} />
              {ENTITLEMENT_LABELS[key]}
            </label>
          ))}
        </fieldset>
        <div className="grid gap-2 sm:flex md:col-span-4">
          <Button className="w-full sm:w-auto" type="submit" disabled={save.isPending}>{editing ? "حفظ التعديل" : "إنشاء باقة"}</Button>
          {editing && <Button className="w-full sm:w-auto" variant="secondary" onClick={() => setEditingId(null)}>إلغاء</Button>}
        </div>
        <div className="md:col-span-4"><ErrorLine error={save.error} /></div>
      </form>}
      <div className="grid gap-3 md:grid-cols-2">
        {plans.map((plan) => (
          <article key={plan.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="font-bold text-slate-900">{plan.name_ar}</h3>
                <p className="text-sm text-slate-500">{plan.code} · {plan.price_amount} {plan.currency}</p>
              </div>
              <span className={`rounded px-2 py-1 text-xs ${plan.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{plan.is_active ? "متاحة" : "معطلة"}</span>
            </div>
            {canManage && <div className="mt-3 grid grid-cols-2 gap-2 sm:flex">
              <Button variant="secondary" onClick={() => load(plan)}>تعديل</Button>
              <Button variant="danger" disabled={!plan.is_active} onClick={() => void disablePlan(plan.id).then(() => queryClient.invalidateQueries({ queryKey: ["platform", "plans"] }))}>تعطيل</Button>
            </div>}
          </article>
        ))}
      </div>
    </section>
  );
}

function SchoolsPanel({ plans, canManageSchools, canManageAccounts, canManageSubscriptions }: { plans: Plan[]; canManageSchools: boolean; canManageAccounts: boolean; canManageSubscriptions: boolean }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [planFilter, setPlanFilter] = useState("");
  const [expiresSoon, setExpiresSoon] = useState(false);
  const [overLimit, setOverLimit] = useState(false);
  const [selected, setSelected] = useState<SchoolRow | null>(null);
  const detailRef = useRef<HTMLElement>(null);
  const filters = { search, status: statusFilter, plan: planFilter, expires_soon: expiresSoon, over_limit: overLimit };
  const schools = useQuery({ queryKey: ["platform", "schools", filters], queryFn: ({ signal }) => getPlatformSchools(filters, signal) });
  const detail = useQuery({ queryKey: ["platform", "school", selected?.id], queryFn: ({ signal }) => getSchoolDetail(selected!.id, signal), enabled: Boolean(selected) });
  const history = useQuery({ queryKey: ["platform", "subscription", selected?.id], queryFn: ({ signal }) => getSubscriptionHistory(selected!.id, signal), enabled: Boolean(selected) });
  const events = useQuery({ queryKey: ["platform", "events", selected?.id], queryFn: ({ signal }) => getSubscriptionEvents(selected!.id, signal), enabled: Boolean(selected) });
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ school_name: "", school_type: "" as SchoolType | "", manager_name: "", manager_mobile: "", plan_id: "", subscription_mode: "TRIAL" as "TRIAL" | "ACTIVE", trial_days: 30, months: 12 });
  const [actionPlanId, setActionPlanId] = useState("");
  const [actionDays, setActionDays] = useState(30);
  const [subscriptionAction, setSubscriptionAction] = useState<SubscriptionActionName>("activate");
  const [actionReason, setActionReason] = useState("إجراء من إدارة المنصة");
  const [actionNotice, setActionNotice] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleteNotice, setDeleteNotice] = useState("");
  const preview = useQuery({
    queryKey: ["platform", "plan-preview", selected?.id, actionPlanId],
    queryFn: ({ signal }) => getPlanChangePreview(selected!.id, Number(actionPlanId), signal),
    enabled: Boolean(canManageSubscriptions && selected && actionPlanId && subscriptionAction === "change-plan"),
  });
  const [createdCredentials, setCreatedCredentials] = useState<{
    mobile: string;
    password: string | null;
    schoolType: SchoolType;
  } | null>(null);
  const createSchool = useMutation({
    mutationFn: () => createPlatformSchool({ ...createForm, school_type: createForm.school_type as SchoolType, plan_id: createForm.plan_id ? Number(createForm.plan_id) : undefined }),
    onSuccess: async (row) => {
      setCreatedCredentials({
        mobile: createForm.manager_mobile,
        password: row.temporary_password,
        schoolType: row.school_type,
      });
      setSelected(row);
      setActionPlanId(plans.find((plan) => plan.code === row.plan)?.id.toString() ?? "");
      setSubscriptionAction(defaultSubscriptionAction(row.subscription_status));
      setCreateForm({ school_name: "", school_type: "", manager_name: "", manager_mobile: "", plan_id: "", subscription_mode: "TRIAL", trial_days: 30, months: 12 });
      setCreateOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["platform", "schools"] });
    },
  });
  const action = useMutation({
    mutationFn: ({ name, body }: { name: string; body: Record<string, unknown> }) => runSubscriptionAction(selected!.id, name, body),
    onSuccess: async (_, variables) => {
      setActionNotice(`تم ${SUBSCRIPTION_ACTION_LABELS[variables.name as SubscriptionActionName]} بنجاح.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["platform", "schools"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "overview"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "school", selected?.id] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "subscription", selected?.id] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "events", selected?.id] }),
      ]);
    },
  });
  const deleteSchool = useMutation({
    mutationFn: () => deletePlatformSchool(detail.data!.id, deleteConfirmation),
    onSuccess: async (result) => {
      setSelected(null);
      setDeleteOpen(false);
      setDeleteConfirmation("");
      setDeleteNotice(
        result.storage_objects_failed > 0
          ? `حُذفت مدرسة ${result.school_name} وبياناتها، لكن تعذر حذف ${result.storage_objects_failed} ملف من التخزين. راجع السجلات التشغيلية.`
          : `حُذفت مدرسة ${result.school_name} وجميع بياناتها نهائيًا.`,
      );
      queryClient.removeQueries({ queryKey: ["platform", "school", result.school_id] });
      queryClient.removeQueries({ queryKey: ["platform", "subscription", result.school_id] });
      queryClient.removeQueries({ queryKey: ["platform", "events", result.school_id] });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["platform", "schools"] }),
        queryClient.invalidateQueries({ queryKey: ["platform", "overview"] }),
      ]);
    },
  });

  useEffect(() => {
    if (detail.data?.id && window.innerWidth < 1280) {
      detailRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    }
  }, [detail.data?.id]);

  const chooseSchool = (school: SchoolRow) => {
    setSelected(school);
    setDeleteOpen(false);
    setDeleteConfirmation("");
    deleteSchool.reset();
    setActionPlanId(plans.find((plan) => plan.code === school.plan)?.id.toString() ?? "");
    setSubscriptionAction(defaultSubscriptionAction(school.subscription_status));
    setActionDays(school.subscription_status === "ACTIVE" ? 30 : 12);
    setActionNotice("");
  };

  const subscriptionActions = subscriptionActionsFor(detail.data?.subscription.status ?? selected?.subscription_status ?? null);
  const actionNeedsPlan = ["start-trial", "activate", "change-plan"].includes(subscriptionAction);
  const actionNeedsDuration = ["start-trial", "extend-trial", "activate", "extend"].includes(subscriptionAction);
  const durationLabel = subscriptionAction === "activate" ? "مدة الاشتراك بالأشهر" : subscriptionAction.includes("trial") ? "المدة بالأيام" : "أيام التمديد";

  const runPrimarySubscriptionAction = () => {
    const body: Record<string, unknown> = { reason: actionReason };
    if (actionNeedsPlan) body.plan_id = Number(actionPlanId);
    if (subscriptionAction === "activate") body.months = actionDays;
    if (subscriptionAction === "start-trial") body.trial_days = actionDays;
    if (subscriptionAction === "extend" || subscriptionAction === "extend-trial") body.days = actionDays;
    action.mutate({ name: subscriptionAction, body });
  };

  return (
    <section className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_560px]">
      <div className="order-2 min-w-0 space-y-3 xl:order-1">
        {deleteNotice && <p role="status" className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-bold text-emerald-800">{deleteNotice}</p>}
        {canManageSchools && <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="font-black text-slate-950">إضافة مدرسة واشتراكها</h2>
              <p className="mt-1 text-xs leading-5 text-slate-500">أنشئ المدرسة وحساب المدير والاشتراك في خطوة واحدة.</p>
            </div>
            <Button type="button" variant={createOpen ? "secondary" : "primary"} onClick={() => setCreateOpen((open) => !open)}>{createOpen ? "إغلاق النموذج" : "إضافة مدرسة جديدة"}</Button>
          </div>
          {createOpen && (
            <form onSubmit={(e) => { e.preventDefault(); createSchool.mutate(); }} className="mt-4 space-y-5 border-t border-slate-100 pt-4">
              <fieldset>
                <legend className="mb-3 text-sm font-black text-slate-800">1. بيانات المدرسة والمدير</legend>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-sm font-medium text-slate-700">اسم المدرسة<input required className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5" placeholder="اسم المدرسة" value={createForm.school_name} onChange={(e) => setCreateForm({ ...createForm, school_name: e.target.value })} /></label>
                  <label className="text-sm font-medium text-slate-700">نوع المدرسة<select aria-label="نوع المدرسة الجديدة" required className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5" value={createForm.school_type} onChange={(e) => setCreateForm({ ...createForm, school_type: e.target.value as SchoolType })}><option value="" disabled>اختر النوع</option><option value="BOYS">بنين</option><option value="GIRLS">بنات</option></select></label>
                  <label className="text-sm font-medium text-slate-700">{createForm.school_type === "GIRLS" ? "اسم المديرة" : "اسم المدير"}<input required className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5" placeholder={createForm.school_type === "GIRLS" ? "اسم المديرة" : createForm.school_type === "BOYS" ? "اسم المدير" : "اسم المدير/المديرة"} value={createForm.manager_name} onChange={(e) => setCreateForm({ ...createForm, manager_name: e.target.value })} /></label>
                  <label className="text-sm font-medium text-slate-700">{createForm.school_type === "GIRLS" ? "جوال المديرة" : "جوال المدير"}<input required dir="ltr" className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5 text-start" placeholder={createForm.school_type === "GIRLS" ? "جوال المديرة" : createForm.school_type === "BOYS" ? "جوال المدير" : "جوال المدير/المديرة"} value={createForm.manager_mobile} onChange={(e) => setCreateForm({ ...createForm, manager_mobile: e.target.value })} /></label>
                </div>
              </fieldset>
              <fieldset className="rounded-2xl bg-slate-50 p-4">
                <legend className="px-1 text-sm font-black text-slate-800">2. الاشتراك</legend>
                <div className="mt-2 grid gap-3 sm:grid-cols-3">
                  <label className="text-sm font-medium text-slate-700">الباقة<select aria-label="باقة الاشتراك عند الإنشاء" className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5" value={createForm.plan_id} onChange={(e) => { const selectedPlan = plans.find((plan) => plan.id === Number(e.target.value)); setCreateForm({ ...createForm, plan_id: e.target.value, trial_days: selectedPlan?.trial_days_default ?? 30 }); }}><option value="">إنشاء بدون اشتراك</option>{plans.filter((plan) => plan.is_active).map((plan) => <option key={plan.id} value={plan.id}>{plan.name_ar}</option>)}</select></label>
                  {createForm.plan_id && <label className="text-sm font-medium text-slate-700">نوع الاشتراك<select aria-label="نوع الاشتراك عند الإنشاء" className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5" value={createForm.subscription_mode} onChange={(e) => setCreateForm({ ...createForm, subscription_mode: e.target.value as "TRIAL" | "ACTIVE" })}><option value="TRIAL">فترة تجريبية</option><option value="ACTIVE">اشتراك نشط</option></select></label>}
                  {createForm.plan_id && <label className="text-sm font-medium text-slate-700">{createForm.subscription_mode === "TRIAL" ? "مدة التجربة بالأيام" : "مدة الاشتراك بالأشهر"}<input aria-label="مدة الاشتراك عند الإنشاء" min={1} required type="number" className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5" value={createForm.subscription_mode === "TRIAL" ? createForm.trial_days : createForm.months} onChange={(e) => setCreateForm({ ...createForm, [createForm.subscription_mode === "TRIAL" ? "trial_days" : "months"]: Number(e.target.value) })} /></label>}
                </div>
              </fieldset>
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between"><ErrorLine error={createSchool.error} /><Button className="w-full sm:w-auto" type="submit" disabled={createSchool.isPending || !createForm.school_type || !createForm.school_name.trim() || !createForm.manager_name.trim() || !createForm.manager_mobile.trim()}>{createForm.plan_id ? "إنشاء المدرسة والاشتراك" : "إنشاء المدرسة بدون اشتراك"}</Button></div>
            </form>
          )}
          {createdCredentials && <div className="mt-4"><CredentialNotice mobile={createdCredentials.mobile} password={createdCredentials.password} managerLabel={createdCredentials.schoolType === "GIRLS" ? "المديرة" : "المدير"} onClose={() => setCreatedCredentials(null)} /></div>}
        </section>}
        <div className="grid gap-2 rounded-2xl border border-slate-200 bg-white p-3 sm:grid-cols-2 xl:grid-cols-5">
          <input className="min-h-11 rounded-xl border border-slate-300 px-3 py-2" placeholder="بحث في المدارس" value={search} onChange={(e) => setSearch(e.target.value)} />
          <select aria-label="حالة الاشتراك" className="min-h-11 rounded-xl border border-slate-300 px-3 py-2" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">كل الحالات</option>
            {(["TRIAL", "ACTIVE", "GRACE_PERIOD", "EXPIRED", "SUSPENDED", "CANCELLED"] as const).map((value) => <option key={value} value={value}>{statusLabel(value)}</option>)}
          </select>
          <select aria-label="الباقة" className="min-h-11 rounded-xl border border-slate-300 px-3 py-2" value={planFilter} onChange={(e) => setPlanFilter(e.target.value)}>
            <option value="">كل الباقات</option>
            {plans.map((plan) => <option key={plan.id} value={plan.code}>{plan.name_ar}</option>)}
          </select>
          <label className="flex min-h-11 items-center gap-2 rounded-xl bg-slate-50 px-3 text-sm"><input className="size-4" type="checkbox" checked={expiresSoon} onChange={(e) => setExpiresSoon(e.target.checked)} />تنتهي قريبًا</label>
          <label className="flex min-h-11 items-center gap-2 rounded-xl bg-slate-50 px-3 text-sm"><input className="size-4" type="checkbox" checked={overLimit} onChange={(e) => setOverLimit(e.target.checked)} />فوق الحد</label>
        </div>
        {schools.isPending ? <Spinner label="جارٍ تحميل المدارس..." /> : (
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            {(schools.data?.results ?? []).map((school) => (
              <button key={school.id} aria-pressed={selected?.id === school.id} className={`flex min-h-16 w-full items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 text-start last:border-b-0 hover:bg-slate-50 ${selected?.id === school.id ? "bg-teal-50/70 ring-1 ring-inset ring-teal-200" : ""}`} onClick={() => chooseSchool(school)}>
                <span className="min-w-0"><b className="block truncate">{school.name}</b><span className="mt-1 block truncate text-xs text-slate-500">{school.plan_name ?? "بدون باقة"} · {school.manager?.name ?? "بلا مدير"}</span></span>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${statusClass(school.subscription_status)}`}>{statusLabel(school.subscription_status)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <aside ref={detailRef} className="order-1 min-w-0 scroll-mt-36 space-y-3 xl:order-2 xl:sticky xl:top-6 xl:max-h-[calc(100vh-3rem)] xl:overflow-y-auto xl:pe-1">
        {!selected && <div className="hidden rounded-2xl border border-slate-200 bg-white p-4 text-slate-600 xl:block">اختر مدرسة لعرض الاشتراك والاستخدام.</div>}
        {detail.data && (
          <>
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div><h3 className="font-black text-slate-900">إدارة الاشتراك</h3><p className="mt-1 text-sm text-slate-500">{detail.data.subscription.plan?.name ?? "بدون اشتراك"} · {statusLabel(detail.data.subscription.status)}</p></div>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${statusClass(detail.data.subscription.status)}`}>{statusLabel(detail.data.subscription.status)}</span>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-3 text-xs">
                <div><dt className="text-slate-500">بداية الاشتراك</dt><dd className="font-semibold text-slate-800">{formatDate(detail.data.subscription.starts_at)}</dd></div>
                <div><dt className="text-slate-500">نهاية الاشتراك</dt><dd className="font-semibold text-slate-800">{formatDate(detail.data.subscription.ends_at)}</dd></div>
                <div><dt className="text-slate-500">نهاية التجربة</dt><dd className="font-semibold text-slate-800">{formatDate(detail.data.subscription.trial_ends_at)}</dd></div>
                <div><dt className="text-slate-500">نهاية السماح</dt><dd className="font-semibold text-slate-800">{formatDate(detail.data.subscription.grace_ends_at)}</dd></div>
                <div><dt className="text-slate-500">الأيام المتبقية</dt><dd className="font-semibold text-slate-800">{detail.data.subscription.days_remaining ?? "—"}</dd></div>
                <div><dt className="text-slate-500">صلاحية الاستخدام</dt><dd className="font-semibold text-slate-800">{detail.data.subscription.access_mode === "FULL" ? "كاملة" : detail.data.subscription.access_mode === "READ_ONLY" ? "قراءة فقط" : "محجوبة"}</dd></div>
              </dl>
              {canManageSubscriptions && <form className="mt-4 rounded-2xl border border-teal-100 bg-teal-50/60 p-3" onSubmit={(event) => { event.preventDefault(); runPrimarySubscriptionAction(); }}>
                <p className="mb-3 text-sm font-black text-teal-950">إضافة أو تحديث الاشتراك</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-sm font-medium text-slate-700">الإجراء<select aria-label="إجراء الاشتراك" className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5" value={subscriptionAction} onChange={(event) => { setSubscriptionAction(event.target.value as SubscriptionActionName); setActionNotice(""); }}>
                    {subscriptionActions.map((name) => <option key={name} value={name}>{SUBSCRIPTION_ACTION_LABELS[name]}</option>)}
                  </select></label>
                  {actionNeedsPlan && <label className="text-sm font-medium text-slate-700">الباقة<select aria-label="الباقة الجديدة" required className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5" value={actionPlanId} onChange={(e) => setActionPlanId(e.target.value)}><option value="">اختر الباقة</option>{plans.filter((plan) => plan.is_active).map((plan) => <option key={plan.id} value={plan.id}>{plan.name_ar}</option>)}</select></label>}
                  {actionNeedsDuration && <label className="text-sm font-medium text-slate-700">{durationLabel}<input aria-label="المدة" min={1} required className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm" type="number" value={actionDays} onChange={(e) => setActionDays(Number(e.target.value))} /></label>}
                </div>
              {preview.data?.plan && (
                <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600" data-testid="plan-change-preview">
                  <p className="font-semibold">معاينة {preview.data.plan.name}</p>
                  {Object.entries(preview.data.impact).map(([key, value]) => (
                    <p key={key} className={value.over_limit ? "font-semibold text-red-700" : ""}>{ENTITLEMENT_LABELS[key] ?? key}: {"used_gb" in value ? value.used_gb : value.used} / {"new_limit_gb" in value ? value.new_limit_gb ?? "بلا حد" : value.new_limit ?? "بلا حد"}{value.over_limit ? " · تجاوز الحد" : ""}</p>
                  ))}
                  <p>لن تُحذف أي بيانات.</p>
                </div>
              )}
                <Button className="mt-3 w-full" type="submit" disabled={action.isPending || (actionNeedsPlan && !actionPlanId) || (actionNeedsDuration && actionDays < 1)}>{action.isPending ? "جارٍ الحفظ..." : SUBSCRIPTION_ACTION_LABELS[subscriptionAction]}</Button>
              </form>}
              {actionNotice && <p role="status" className="mt-3 rounded-xl bg-emerald-50 p-3 text-sm font-bold text-emerald-800">{actionNotice}</p>}
              {canManageSubscriptions && <details className="mt-3 rounded-xl border border-slate-200 p-3">
                <summary className="cursor-pointer text-sm font-bold text-slate-700">إجراءات متقدمة</summary>
                <label className="mt-3 block text-sm font-medium text-slate-700">سبب الإجراء<input aria-label="سبب إجراء الاشتراك" className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5" value={actionReason} onChange={(event) => setActionReason(event.target.value)} /></label>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {detail.data.subscription.has_subscription && detail.data.subscription.status !== "SUSPENDED" && <Button variant="danger" disabled={action.isPending || !actionReason.trim()} onClick={() => action.mutate({ name: "suspend", body: { reason: actionReason } })}>إيقاف</Button>}
                  {detail.data.subscription.has_subscription && <Button variant="danger" disabled={action.isPending || !actionReason.trim()} onClick={() => action.mutate({ name: "cancel", body: { reason: actionReason } })}>إلغاء</Button>}
                </div>
              </details>}
              <ErrorLine error={action.error} />
            </div>
            <SchoolAccountManagement key={detail.data.id} detail={detail.data} canManageSchool={canManageSchools} canManageAccounts={canManageAccounts} />
            <UsageGrid usage={detail.data.usage} />
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h4 className="mb-2 font-bold">السجل</h4>
              {(history.data?.history ?? []).slice(0, 4).map((row) => <p key={row.id} className="text-sm text-slate-600">{row.plan_name} · {statusLabel(row.status)}</p>)}
              {(events.data ?? []).slice(0, 5).map((event) => <p key={event.id} className="mt-1 text-xs text-slate-500">{event.event_type} · {new Date(event.created_at).toLocaleDateString("ar-SA")}</p>)}
            </div>
            {canManageSchools && <div className="rounded-2xl border border-red-200 bg-red-50/60 p-4">
              <div className="flex items-start gap-3">
                <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-red-100 text-red-700"><Trash2 aria-hidden size={19} /></span>
                <div className="min-w-0 flex-1">
                  <h4 className="font-black text-red-950">منطقة الخطر</h4>
                  <p className="mt-1 text-xs leading-5 text-red-800">يحذف المدرسة والطلاب والموظفين والحضور والاشتراكات والسجلات والملفات نهائيًا. لا يمكن التراجع عن هذا الإجراء.</p>
                </div>
              </div>
              {!deleteOpen ? (
                <Button className="mt-4 w-full" variant="danger" onClick={() => setDeleteOpen(true)}>حذف المدرسة نهائيًا</Button>
              ) : (
                <form className="mt-4 rounded-xl border border-red-200 bg-white p-3" onSubmit={(event) => { event.preventDefault(); deleteSchool.mutate(); }}>
                  <p className="text-sm font-bold text-red-950">للتأكيد، اكتب اسم المدرسة كما هو:</p>
                  <p className="mt-1 break-words text-sm font-black text-slate-900">{detail.data.name}</p>
                  <input
                    aria-label="اكتب اسم المدرسة للتأكيد"
                    autoComplete="off"
                    className="mt-3 w-full rounded-xl border border-red-300 px-3 py-2.5"
                    value={deleteConfirmation}
                    onChange={(event) => setDeleteConfirmation(event.target.value)}
                  />
                  <div className="mt-3 flex flex-col-reverse gap-2 sm:flex-row">
                    <Button variant="secondary" className="flex-1" disabled={deleteSchool.isPending} onClick={() => { setDeleteOpen(false); setDeleteConfirmation(""); deleteSchool.reset(); }}>تراجع</Button>
                    <Button type="submit" variant="danger" className="flex-1" disabled={deleteSchool.isPending || deleteConfirmation.trim() !== detail.data.name}>{deleteSchool.isPending ? "جارٍ الحذف النهائي..." : "تأكيد الحذف النهائي"}</Button>
                  </div>
                  <ErrorLine error={deleteSchool.error} />
                </form>
              )}
            </div>}
          </>
        )}
      </aside>
    </section>
  );
}

export function PlatformAdminPage() {
  const [tab, setTab] = useState<PlatformTab>("dashboard");
  const logout = useLogout();
  const navigate = useNavigate();
  const me = useMe();
  const hasCapability = (capability: PlatformCapability) => {
    const declared = me.data?.platform_capabilities;
    return Boolean(me.data?.is_platform_owner) ||
      ((declared?.length ?? 0) > 0 ? Boolean(declared?.includes(capability)) : Boolean(me.data?.is_platform_admin));
  };
  const visibleTabs = PLATFORM_TABS.filter((item) => item.capability === null || hasCapability(item.capability));
  const overview = useQuery({ queryKey: ["platform", "overview"], queryFn: ({ signal }) => getPlatformOverview(signal), enabled: hasCapability("DASHBOARD_VIEW") });
  const plans = useQuery({ queryKey: ["platform", "plans"], queryFn: ({ signal }) => getPlans(signal), enabled: hasCapability("PLANS_VIEW") });
  const activePlans = useMemo(() => plans.data ?? [], [plans.data]);
  const currentTab = visibleTabs.some((item) => item.id === tab) ? tab : (visibleTabs[0]?.id ?? "account");
  const activeTab = visibleTabs.find((item) => item.id === currentTab) ?? PLATFORM_TABS[4]!;
  const today = new Intl.DateTimeFormat("ar-SA", { weekday: "long", day: "numeric", month: "long" }).format(new Date());
  const handleLogout = () => void logout().then(() => navigate("/login", { replace: true }));

  return (
    <>
    <a className="skip-link" href="#platform-main-content">الانتقال إلى المحتوى</a>
    <main id="platform-main-content" tabIndex={-1} className="min-h-screen bg-slate-50 px-4 py-4 sm:px-6 lg:px-8 lg:py-6">
      <div className="mx-auto flex max-w-screen-2xl gap-6">
        <aside className="sticky top-6 hidden h-[calc(100vh-3rem)] w-72 shrink-0 flex-col overflow-hidden rounded-3xl bg-slate-950 text-white shadow-2xl shadow-slate-950/15 xl:flex">
          <div className="border-b border-white/10 px-5 py-6">
            <div className="flex items-center gap-3">
              <span className="grid size-11 place-items-center rounded-2xl bg-gradient-to-br from-teal-400 to-emerald-600 shadow-lg shadow-teal-950/30"><ShieldCheck aria-hidden size={22} /></span>
              <div><p className="font-black">منصة المواظبة</p><p className="mt-0.5 text-[11px] font-medium text-slate-400">مركز إدارة المنصة</p></div>
            </div>
          </div>

          <nav aria-label="أقسام إدارة المنصة" className="flex-1 space-y-2 p-4">
            <p className="mb-3 px-3 text-[11px] font-bold tracking-wide text-slate-500">مساحة العمل</p>
            {visibleTabs.map((item) => {
              const Icon = item.icon;
              const selected = currentTab === item.id;
              return (
                <button key={item.id} type="button" aria-current={selected ? "page" : undefined} onClick={() => setTab(item.id)} className={`group flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-start transition ${selected ? "bg-white/10 text-white ring-1 ring-white/10" : "text-slate-300 hover:bg-white/5 hover:text-white"}`}>
                  <span className={`grid size-10 shrink-0 place-items-center rounded-xl transition ${selected ? "bg-teal-400 text-slate-950" : "bg-white/5 text-slate-400 group-hover:text-teal-300"}`}><Icon aria-hidden size={19} /></span>
                  <span><span className="block text-sm font-bold">{item.label}</span><span className={`mt-0.5 block text-[11px] ${selected ? "text-slate-300" : "text-slate-500"}`}>{item.description}</span></span>
                </button>
              );
            })}
          </nav>

          <div className="border-t border-white/10 p-4">
            <button type="button" onClick={() => setTab("account")} className="mb-3 flex w-full items-center gap-3 rounded-2xl bg-white/5 p-3 text-start transition hover:bg-white/10">
              <span className="grid size-9 shrink-0 place-items-center rounded-full bg-teal-400/15 text-sm font-black text-teal-200">{me.data?.name?.trim().charAt(0) || "م"}</span>
              <div className="min-w-0"><p className="truncate text-sm font-bold">{me.data?.name ?? "مشرف المنصة"}</p><p className="mt-0.5 text-[11px] text-slate-500">{me.data?.platform_role_label || "إدارة المنصة"}</p></div>
            </button>
            <button type="button" onClick={handleLogout} className="flex w-full items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-bold text-slate-400 transition hover:bg-red-500/10 hover:text-red-300"><LogOut aria-hidden size={17} />تسجيل الخروج</button>
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-20 -mx-4 mb-5 border-b border-slate-200/80 bg-slate-100/90 px-4 py-3 backdrop-blur-xl sm:-mx-6 sm:px-6 lg:static lg:mx-0 lg:border-0 lg:bg-transparent lg:px-0 lg:pb-0 lg:pt-1">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="mb-1 hidden items-center gap-1.5 text-xs font-semibold text-slate-500 sm:flex"><CalendarClock aria-hidden size={14} />{today}</p>
                <h1 className="truncate text-xl font-black text-slate-950 sm:text-2xl">إدارة المنصة</h1>
                <p className="mt-1 hidden text-sm text-slate-500 sm:block">{activeTab.description} · دون تصفح بيانات الطلاب</p>
              </div>
              <div className="flex items-center gap-2">
                {currentTab === "dashboard" && (
                  <button type="button" onClick={() => void overview.refetch()} disabled={overview.isFetching} className="inline-flex size-11 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-teal-300 hover:text-teal-700 disabled:opacity-60 sm:w-auto sm:px-3" aria-label="تحديث المؤشرات">
                    <RefreshCw aria-hidden size={17} className={overview.isFetching ? "animate-spin" : ""} /><span className="ms-2 hidden text-sm font-bold sm:inline">تحديث</span>
                  </button>
                )}
                <button type="button" onClick={handleLogout} className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm font-bold text-slate-600 shadow-sm transition hover:border-red-200 hover:bg-red-50 hover:text-red-700 xl:hidden" aria-label="تسجيل الخروج"><LogOut aria-hidden size={17} /><span>تسجيل الخروج</span></button>
              </div>
            </div>
            <nav aria-label="أقسام إدارة المنصة" className="mt-3 flex gap-1 overflow-x-auto rounded-2xl border border-slate-200 bg-white p-1 shadow-sm xl:hidden">
              {visibleTabs.map((item) => {
                const Icon = item.icon;
                return <button key={item.id} type="button" onClick={() => setTab(item.id)} className={`flex shrink-0 items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs font-bold transition sm:text-sm ${currentTab === item.id ? "bg-slate-950 text-white shadow-sm" : "text-slate-500 hover:bg-slate-50"}`}><Icon aria-hidden size={16} />{item.label}</button>;
              })}
            </nav>
          </header>

          {currentTab === "dashboard" && (
            overview.isPending ? <div className="rounded-2xl border border-slate-200 bg-white p-8"><Spinner label="جارٍ تحميل لوحة المنصة..." /></div> : overview.isError || !overview.data ? (
              <section className="rounded-2xl border border-red-200 bg-white p-6 text-center"><AlertTriangle aria-hidden className="mx-auto text-red-500" /><h2 className="mt-3 font-black text-slate-900">تعذر تحميل مؤشرات المنصة</h2><p className="mt-1 text-sm text-slate-500">تحقق من الاتصال ثم أعد المحاولة.</p><Button className="mt-4" onClick={() => void overview.refetch()}>إعادة المحاولة</Button></section>
            ) : <DashboardPanel overview={overview.data} onOpenSchools={() => setTab("schools")} />
          )}
          {currentTab === "schools" && <SchoolsPanel plans={activePlans} canManageSchools={hasCapability("SCHOOLS_MANAGE")} canManageAccounts={hasCapability("SCHOOL_ACCOUNTS_MANAGE")} canManageSubscriptions={hasCapability("SUBSCRIPTIONS_MANAGE")} />}
          {currentTab === "plans" && (plans.isPending ? <div className="rounded-2xl border border-slate-200 bg-white p-8"><Spinner label="جارٍ تحميل الباقات..." /></div> : <PlanForm plans={activePlans} canManage={hasCapability("PLANS_MANAGE")} />)}
          {currentTab === "team" && <PlatformTeamPanel canManage={hasCapability("TEAM_MANAGE")} currentUserId={me.data?.id} />}
          {currentTab === "account" && <PlatformAccountPanel />}
        </div>
      </div>
    </main>
    </>
  );
}
