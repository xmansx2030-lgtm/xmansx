import {
  BarChart3, BellRing, BookOpenCheck, Building2, CreditCard, FileSpreadsheet, Fingerprint,
  ChevronDown, DoorOpen, GraduationCap, HeartHandshake, LayoutDashboard, LogOut, Menu,
  MessageSquareMore, QrCode, RefreshCw, Send, Settings, Sunrise,
  UsersRound, X, type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { SchoolSwitcher } from "@/features/auth/SchoolSwitcher";
import { useLogout, useMe } from "@/features/auth/useMe";
import { roleLabels, studentPluralLabel } from "@/utils/roles";
import type { SchoolCapability, SchoolRole } from "@/types/auth";

type Role = SchoolRole;
type NavigationGroup = "overview" | "students" | "operations" | "management";

interface NavigationItem {
  to: string;
  label: string;
  roles: Role[];
  capabilities?: SchoolCapability[];
  icon: LucideIcon;
  group: NavigationGroup;
}

const MANAGER_VP: Role[] = ["SCHOOL_MANAGER", "VICE_PRINCIPAL"];
const MANAGER_VP_COUNSELOR: Role[] = [...MANAGER_VP, "COUNSELOR"];
const VICE_PRINCIPAL_PRIMARY_PATHS = new Set([
  "/dashboard",
  "/reports",
  "/attendance/monitoring",
  "/excuses",
  "/student-leaves",
]);
const MANAGER_PRIMARY_PATHS = new Set([
  "/dashboard",
  "/reports",
  "/students",
  "/attendance/monitoring",
  "/staff",
  "/settings",
]);

const GROUP_LABELS: Record<NavigationGroup, string> = {
  overview: "نظرة عامة",
  students: "الطلاب والمتابعة",
  operations: "الحضور والتشغيل",
  management: "إدارة المدرسة",
};

const NAVIGATION: NavigationItem[] = [
  { to: "/dashboard", label: "لوحة الإدارة", roles: MANAGER_VP, icon: LayoutDashboard, group: "overview" },
  { to: "/reports", label: "التقارير", roles: MANAGER_VP, icon: FileSpreadsheet, group: "overview" },
  { to: "/", label: "التحضير", roles: ["TEACHER"], icon: BookOpenCheck, group: "overview" },
  { to: "/students", label: "الطلاب", roles: MANAGER_VP_COUNSELOR, icon: GraduationCap, group: "students" },
  { to: "/warnings", label: "الإنذارات", roles: MANAGER_VP, icon: BellRing, group: "students" },
  { to: "/excuses", label: "الأعذار", roles: MANAGER_VP_COUNSELOR, icon: BookOpenCheck, group: "students" },
  { to: "/referrals", label: "الإحالات", roles: MANAGER_VP_COUNSELOR, icon: Send, group: "students" },
  { to: "/counselor", label: "الإرشاد", roles: MANAGER_VP_COUNSELOR, icon: HeartHandshake, group: "students" },
  { to: "/teacher/follow-ups", label: "طلبات المتابعة", roles: ["TEACHER"], icon: MessageSquareMore, group: "students" },
  { to: "/referrals/mine", label: "التحويلات", roles: ["TEACHER"], icon: Send, group: "students" },
  { to: "/attendance/monitoring", label: "متابعة التحضير", roles: MANAGER_VP, icon: BookOpenCheck, group: "operations" },
  { to: "/attendance/analytics", label: "الغياب والحضور", roles: MANAGER_VP, icon: BarChart3, group: "operations" },
  { to: "/morning", label: "التأخر الصباحي", roles: MANAGER_VP, capabilities: ["MORNING_ATTENDANCE"], icon: Sunrise, group: "operations" },
  { to: "/student-leaves", label: "الاستئذانات", roles: MANAGER_VP, icon: DoorOpen, group: "operations" },
  { to: "/gate", label: "بوابة المدرسة", roles: [...MANAGER_VP, "GATE_GUARD"], icon: DoorOpen, group: "operations" },
  { to: "/attendance/qr", label: "رموز QR", roles: ["SCHOOL_MANAGER"], icon: QrCode, group: "operations" },
  { to: "/devices", label: "أجهزة الحضور", roles: ["SCHOOL_MANAGER"], icon: Fingerprint, group: "operations" },
  { to: "/devices/roster-sync", label: "مزامنة أجهزة الطلاب", roles: ["SCHOOL_MANAGER"], icon: RefreshCw, group: "operations" },
  { to: "/staff", label: "الموظفون", roles: MANAGER_VP, icon: UsersRound, group: "management" },
  { to: "/subscription", label: "الاشتراك", roles: ["SCHOOL_MANAGER"], icon: CreditCard, group: "management" },
  { to: "/settings", label: "الإعدادات", roles: ["SCHOOL_MANAGER"], icon: Settings, group: "management" },
];

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className="group flex min-w-0 items-center gap-3" aria-label="الرئيسية — منصة المواظبة">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-teal-500 to-emerald-700 text-white shadow-lg shadow-teal-950/20 transition-transform group-hover:-translate-y-0.5">
        <Building2 aria-hidden size={21} strokeWidth={2.3} />
      </span>
      {!compact && (
        <span className="min-w-0 leading-tight">
          <strong className="block truncate text-base font-black text-white">منصة المواظبة</strong>
          <span className="mt-1 block text-[11px] font-medium text-slate-400">إدارة مدرسية أكثر وضوحًا</span>
        </span>
      )}
    </Link>
  );
}

function NavigationLinks({ items, schoolType, onNavigate }: { items: NavigationItem[]; schoolType?: "BOYS" | "GIRLS"; onNavigate?: () => void }) {
  const groups = (Object.keys(GROUP_LABELS) as NavigationGroup[]).filter((group) =>
    items.some((item) => item.group === group),
  );

  return groups.map((group) => (
    <div key={group} className="mb-5 last:mb-0">
      <p className="mb-2 px-3 text-[11px] font-bold tracking-wide text-slate-500">{group === "students" ? `${studentPluralLabel(schoolType)} والمتابعة` : GROUP_LABELS[group]}</p>
      <div className="space-y-1">
        {items.filter((item) => item.group === group).map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              onClick={onNavigate}
              className={({ isActive }) => `group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 ${isActive ? "bg-white/12 text-white shadow-sm ring-1 ring-white/10" : "text-slate-300 hover:bg-white/7 hover:text-white"}`}
            >
              {({ isActive }) => (
                <>
                  <Icon aria-hidden size={18} className={isActive ? "text-teal-300" : "text-slate-500 transition-colors group-hover:text-teal-300"} />
                  <span>{item.to === "/students" ? studentPluralLabel(schoolType) : item.to === "/devices/roster-sync" ? `مزامنة أجهزة ${studentPluralLabel(schoolType)}` : item.label}</span>
                </>
              )}
            </NavLink>
          );
        })}
      </div>
    </div>
  ));
}

function AdditionalNavigation({ items, schoolType, onNavigate }: { items: NavigationItem[]; schoolType?: "BOYS" | "GIRLS"; onNavigate?: () => void }) {
  if (items.length === 0) return null;
  return (
    <details className="group rounded-xl border border-white/10 bg-white/5" data-testid="additional-navigation">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-xl px-3 py-3 text-sm font-bold text-slate-300 transition hover:bg-white/7 hover:text-white">
        <span>أدوات إضافية</span>
        <ChevronDown aria-hidden size={17} className="transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-white/10 px-1 pt-4">
        <NavigationLinks items={items} schoolType={schoolType} onNavigate={onNavigate} />
      </div>
    </details>
  );
}

function UserPanel({ onLogout, mobile = false }: { onLogout: () => void; mobile?: boolean }) {
  const me = useMe();
  if (!me.isSuccess) return null;
  return (
    <div className={`flex items-center gap-3 ${mobile ? "border-t border-slate-200 p-4" : "border-t border-white/10 p-4"}`}>
      <span className={`grid size-10 shrink-0 place-items-center rounded-full text-sm font-black ${mobile ? "bg-teal-50 text-teal-800" : "bg-white/10 text-teal-200"}`}>
        {me.data.name.trim().charAt(0)}
      </span>
      <div className="min-w-0 flex-1">
        <p className={`truncate text-sm font-bold ${mobile ? "text-slate-900" : "text-white"}`} data-testid={mobile ? "user-name-mobile" : "user-name"}>{me.data.name}</p>
        <p className={`truncate text-xs ${mobile ? "text-slate-500" : "text-slate-400"}`} data-testid={mobile ? "user-roles-mobile" : "user-roles"}>{roleLabels(me.data.roles, me.data.active_school?.school_type)}</p>
      </div>
      <button type="button" onClick={onLogout} aria-label="تسجيل الخروج" title="تسجيل الخروج" className={`grid size-9 shrink-0 place-items-center rounded-lg transition-colors focus-visible:outline-2 ${mobile ? "text-slate-500 hover:bg-slate-100 hover:text-red-700" : "text-slate-400 hover:bg-white/10 hover:text-white"}`}>
        <LogOut aria-hidden size={17} />
      </button>
    </div>
  );
}

/** غلاف موحّد لكل شاشات المدرسة مع تنقل واضح ومتجاوب حسب الصلاحيات. */
export function AppShell() {
  const navigate = useNavigate();
  const me = useMe();
  const doLogout = useLogout();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const schoolType = me.data?.active_school?.school_type;
  const items = me.isSuccess ? NAVIGATION.filter((item) =>
    item.roles.some((role) => me.data.roles.includes(role)) ||
    (item.capabilities ?? []).some((capability) => (me.data.capabilities ?? []).includes(capability)),
  ) : [];
  const isManager = me.isSuccess && me.data.roles.includes("SCHOOL_MANAGER");
  const isVicePrincipalOnly = me.isSuccess && me.data.roles.includes("VICE_PRINCIPAL") && !isManager;
  const primaryPaths = isManager ? MANAGER_PRIMARY_PATHS : isVicePrincipalOnly ? VICE_PRINCIPAL_PRIMARY_PATHS : null;
  const primaryItems = primaryPaths ? items.filter((item) => primaryPaths.has(item.to)) : items;
  const additionalItems = primaryPaths ? items.filter((item) => !primaryPaths.has(item.to)) : [];
  const handleLogout = () => { void doLogout().then(() => navigate("/login", { replace: true })); };

  return (
    <div className="min-h-dvh bg-slate-50 lg:flex">
      <a className="skip-link" href="#main-content">الانتقال إلى المحتوى</a>
      <aside className="hidden h-dvh w-70 shrink-0 flex-col overflow-hidden bg-slate-950 lg:sticky lg:top-0 lg:flex">
        <div className="border-b border-white/10 p-5"><Brand /></div>
        <nav aria-label="التنقل الرئيسي" className="flex-1 overflow-y-auto px-3 py-5">
          <NavigationLinks items={primaryItems} schoolType={schoolType} />
          <AdditionalNavigation items={additionalItems} schoolType={schoolType} />
        </nav>
        <UserPanel onLogout={handleLogout} />
      </aside>

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/90 px-4 py-3 shadow-sm backdrop-blur-xl lg:px-8">
          <div className="mx-auto flex max-w-7xl items-center gap-3">
            <div className="rounded-xl bg-slate-950 p-1.5 lg:hidden"><Brand compact /></div>
            <div className="min-w-0 flex-1"><SchoolSwitcher /></div>
            <button type="button" aria-label={mobileMenuOpen ? "إغلاق قائمة التنقل" : "فتح قائمة التنقل"} aria-expanded={mobileMenuOpen} aria-controls="mobile-navigation" className="grid size-11 shrink-0 place-items-center rounded-xl border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-teal-300 hover:text-teal-800 focus-visible:outline-2 lg:hidden" onClick={() => setMobileMenuOpen((open) => !open)}>
              {mobileMenuOpen ? <X aria-hidden size={20} /> : <Menu aria-hidden size={20} />}
            </button>
          </div>
        </header>

        {mobileMenuOpen && (
          <div className="fixed inset-0 z-30 bg-slate-950/35 pt-[65px] backdrop-blur-sm lg:hidden" onClick={() => setMobileMenuOpen(false)}>
            <nav id="mobile-navigation" aria-label="التنقل الرئيسي" className="ms-auto flex max-h-[calc(100dvh-65px)] w-[min(88vw,22rem)] flex-col overflow-hidden bg-slate-950 shadow-2xl" onClick={(event) => event.stopPropagation()}>
              <div className="flex-1 overflow-y-auto px-4 py-5">
                <NavigationLinks items={primaryItems} schoolType={schoolType} onNavigate={() => setMobileMenuOpen(false)} />
                <AdditionalNavigation items={additionalItems} schoolType={schoolType} onNavigate={() => setMobileMenuOpen(false)} />
              </div>
              <div className="bg-white"><UserPanel onLogout={handleLogout} mobile /></div>
            </nav>
          </div>
        )}

        <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-[94rem] px-4 py-6 sm:px-6 sm:py-8 xl:px-8"><Outlet /></main>
      </div>
    </div>
  );
}
