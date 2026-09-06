import {
  BellRing,
  CalendarDays,
  CalendarRange,
  CheckCircle2,
  Clock3,
  LayoutGrid,
  School,
  Settings2,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { useMe } from "@/features/auth/useMe";
import { AttendanceSettingsTab } from "@/features/settings/tabs/AttendanceSettingsTab";
import { BellSchedulesTab } from "@/features/settings/tabs/BellSchedulesTab";
import { CalendarTab } from "@/features/settings/tabs/CalendarTab";
import { SchoolInfoTab } from "@/features/settings/tabs/SchoolInfoTab";
import { StructureTab } from "@/features/settings/tabs/StructureTab";
import { WarningRulesTab } from "@/features/settings/tabs/WarningRulesTab";
import { WeekDaysTab } from "@/features/settings/tabs/WeekDaysTab";

const TABS = [
  { key: "info", label: "بيانات المدرسة", shortDescription: "الهوية والشعار والبيانات الرسمية", icon: School },
  { key: "calendar", label: "العام الدراسي", shortDescription: "الأعوام والفصول الدراسية", icon: CalendarRange },
  { key: "structure", label: "الصفوف والفصول", shortDescription: "الهيكل الدراسي وخيارات تسجيل الطلاب", icon: LayoutGrid },
  { key: "week-days", label: "أيام الدراسة", shortDescription: "أيام العمل والجدول المطبق", icon: CalendarDays },
  { key: "bell-schedules", label: "أوقات الحصص", shortDescription: "الجداول والحصص اليومية", icon: Clock3 },
  { key: "attendance", label: "إعدادات التحضير", shortDescription: "التنبيهات ومهلة التعديل", icon: CheckCircle2 },
  { key: "warnings", label: "الإنذارات", shortDescription: "حدود إنذارات الغياب والتأخر", icon: BellRing },
] as const satisfies ReadonlyArray<{
  key: string;
  label: string;
  shortDescription: string;
  icon: LucideIcon;
}>;

type TabKey = (typeof TABS)[number]["key"];

function isTabKey(value: string | null): value is TabKey {
  return TABS.some((item) => item.key === value);
}

/** مساحة إعدادات منظمة مع رابط مباشر لكل قسم وصلاحيات واضحة للمستخدم. */
export function SettingsPage() {
  const me = useMe();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("section");
  const tab: TabKey = isTabKey(requestedTab) ? requestedTab : "info";

  const roles = me.data?.roles ?? [];
  const canManage = roles.includes("SCHOOL_MANAGER");
  const activeTab = TABS.find((item) => item.key === tab) ?? TABS[0];

  const selectTab = (key: TabKey) => {
    setSearchParams(key === "info" ? {} : { section: key }, { replace: true });
  };

  if (me.isSuccess && !canManage) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <span className="mx-auto mb-4 grid size-12 place-items-center rounded-2xl bg-slate-100 text-slate-500"><ShieldCheck aria-hidden size={23} /></span>
        <h2 className="mb-2 text-lg font-bold">لا تملك صلاحية عرض الإعدادات</h2>
        <p className="text-slate-600">إعدادات المدرسة متاحة {me.data.active_school?.school_type === "GIRLS" ? "لمديرة المدرسة" : "لمدير المدرسة"} فقط.</p>
      </section>
    );
  }

  return (
    <div className="space-y-6" data-testid="settings-page">
      <header className="overflow-hidden rounded-3xl border border-teal-900/10 bg-gradient-to-l from-slate-950 via-slate-900 to-teal-950 px-5 py-6 text-white shadow-xl shadow-slate-950/10 sm:px-7">
        <div className="flex flex-wrap items-center justify-between gap-5">
          <div className="flex items-center gap-4">
            <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-white/10 text-teal-200 ring-1 ring-white/10">
              <Settings2 aria-hidden size={25} />
            </span>
            <div>
              <p className="mb-1 text-xs font-bold text-teal-300">لوحة التحكم</p>
              <h1 className="text-2xl font-black sm:text-3xl">إعدادات المدرسة</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">اضبط بيانات المدرسة والتقويم والحصص وسياسات المتابعة من مكان واحد.</p>
            </div>
          </div>
          <span className="inline-flex items-center gap-2 rounded-full bg-emerald-400/10 px-3 py-2 text-xs font-bold text-emerald-200 ring-1 ring-emerald-300/20">
            <ShieldCheck aria-hidden size={15} />
            يمكنك التعديل والحفظ
          </span>
        </div>
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-24">
          <nav className="overflow-x-auto rounded-2xl border border-slate-200 bg-white p-2 shadow-sm" role="tablist" aria-label="أقسام إعدادات المدرسة">
            <div className="flex min-w-max gap-1 lg:min-w-0 lg:flex-col">
              {TABS.map((item) => {
                const Icon = item.icon;
                const selected = tab === item.key;
                return (
                  <button
                    key={item.key}
                    type="button"
                    role="tab"
                    id={`settings-tab-${item.key}`}
                    aria-label={item.label}
                    aria-selected={selected}
                    aria-controls={`settings-panel-${item.key}`}
                    onClick={() => selectTab(item.key)}
                    className={`group flex min-w-42 items-center gap-3 rounded-xl px-3 py-3 text-start transition-all lg:min-w-0 ${selected ? "bg-blue-50 text-blue-800 ring-1 ring-blue-100" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}
                  >
                    <span className={`grid size-9 shrink-0 place-items-center rounded-xl ${selected ? "bg-blue-600 text-white shadow-sm" : "bg-slate-100 text-slate-500 group-hover:bg-white"}`}><Icon aria-hidden size={18} /></span>
                    <span className="min-w-0">
                      <strong className="block text-sm">{item.label}</strong>
                      <span className="mt-0.5 hidden truncate text-[11px] font-normal text-slate-500 lg:block">{item.shortDescription}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </nav>
        </aside>

        <section
          id={`settings-panel-${tab}`}
          role="tabpanel"
          aria-labelledby={`settings-tab-${tab}`}
          className="min-w-0"
        >
          <div className="mb-5 flex items-start gap-3 border-b border-slate-200 pb-4">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-100 text-blue-700"><activeTab.icon aria-hidden size={20} /></span>
            <div>
              <h2 className="text-xl font-black text-slate-900">{activeTab.label}</h2>
              <p className="mt-1 text-sm text-slate-500">{activeTab.shortDescription}</p>
            </div>
          </div>

          {tab === "info" && <SchoolInfoTab canWrite={canManage} />}
          {tab === "calendar" && <CalendarTab canWrite={canManage} />}
          {tab === "structure" && <StructureTab canWrite={canManage} />}
          {tab === "week-days" && <WeekDaysTab canWrite={canManage} />}
          {tab === "bell-schedules" && <BellSchedulesTab canWrite={canManage} />}
          {tab === "attendance" && <AttendanceSettingsTab canWrite={canManage} />}
          {tab === "warnings" && <WarningRulesTab />}
        </section>
      </div>
    </div>
  );
}
