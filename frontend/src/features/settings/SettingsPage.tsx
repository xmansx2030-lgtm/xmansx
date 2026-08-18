import { useState } from "react";

import { useMe } from "@/features/auth/useMe";
import { AttendanceSettingsTab } from "@/features/settings/tabs/AttendanceSettingsTab";
import { BellSchedulesTab } from "@/features/settings/tabs/BellSchedulesTab";
import { CalendarTab } from "@/features/settings/tabs/CalendarTab";
import { SchoolInfoTab } from "@/features/settings/tabs/SchoolInfoTab";
import { WeekDaysTab } from "@/features/settings/tabs/WeekDaysTab";

const TABS = [
  { key: "info", label: "بيانات المدرسة" },
  { key: "calendar", label: "العام الدراسي" },
  { key: "week-days", label: "أيام الدراسة والحصص" },
  { key: "bell-schedules", label: "أوقات الحصص" },
  { key: "attendance", label: "إعدادات التحضير" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

/** صفحة إعدادات المدرسة — الكتابة لمدير المدرسة فقط، والإنفاذ الحقيقي على الخادم. */
export function SettingsPage() {
  const me = useMe();
  const [tab, setTab] = useState<TabKey>("info");

  const roles = me.data?.roles ?? [];
  const canRead = roles.some((r) =>
    ["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR"].includes(r),
  );
  const canWrite = roles.includes("SCHOOL_MANAGER");

  if (me.isSuccess && !canRead) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <h2 className="mb-2 text-lg font-bold">لا تملك صلاحية عرض الإعدادات</h2>
        <p className="text-slate-600">إعدادات المدرسة متاحة للإدارة فقط.</p>
      </section>
    );
  }

  return (
    <div>
      <h2 className="mb-4 text-2xl font-bold">إعدادات المدرسة</h2>

      <nav className="mb-6 flex flex-wrap gap-2 border-b border-slate-200 pb-px" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-t-lg px-4 py-2 text-sm font-medium transition-colors ${
              tab === t.key
                ? "border-b-2 border-blue-600 bg-white text-blue-700"
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === "info" && <SchoolInfoTab canWrite={canWrite} />}
      {tab === "calendar" && <CalendarTab canWrite={canWrite} />}
      {tab === "week-days" && <WeekDaysTab canWrite={canWrite} />}
      {tab === "bell-schedules" && <BellSchedulesTab canWrite={canWrite} />}
      {tab === "attendance" && <AttendanceSettingsTab canWrite={canWrite} />}
    </div>
  );
}
