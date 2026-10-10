import {
  BarChart3, BellRing, BookOpenCheck, Building2, CalendarDays, CreditCard, FileSpreadsheet, Fingerprint,
  ChevronDown, DoorOpen, GraduationCap, HeartHandshake, LayoutDashboard, LogOut, Menu,
  MessageSquareMore, QrCode, RefreshCw, Send, Settings, Sunrise,
  UserRound, UsersRound, X, type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useNavigation } from "react-router-dom";

import { SchoolSwitcher } from "@/features/auth/SchoolSwitcher";
import { SchoolEmailVerificationNotice } from "@/features/auth/SchoolEmailVerificationNotice";
import { useLogout, useMe } from "@/features/auth/useMe";
import { roleLabels, studentPluralLabel } from "@/utils/roles";
import type { SchoolCapability, SchoolRole } from "@/types/auth";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { SpaceSwitchButton } from "@/features/parent/SpaceSwitchButton";
import { Modal } from "@/components/Modal";
import { FeatureSubscriptionNotice, SchoolFeatureBoundary, featureForPath, useSchoolFeatures, type SchoolFeature } from "@/features/platform/schoolFeatures";

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
  "/parent-management",
  "/dashboard",
  "/reports",
  "/warnings",
  "/referrals",
  "/attendance/monitoring",
  "/attendance/absence-messages",
  "/excuses",
  "/student-leaves",
  "/academic-calendar",
]);
const MANAGER_PRIMARY_PATHS = new Set([
  "/parent-management",
  "/dashboard",
  "/reports",
  "/students",
  "/warnings",
  "/excuses",
  "/referrals",
  "/attendance/monitoring",
  "/attendance/absence-messages",
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
  { to: "/reports", label: "التقارير", roles: MANAGER_VP_COUNSELOR, icon: FileSpreadsheet, group: "overview" },
  { to: "/workspace", label: "التحضير", roles: ["TEACHER"], icon: BookOpenCheck, group: "overview" },
  { to: "/students", label: "الطلاب", roles: MANAGER_VP_COUNSELOR, icon: GraduationCap, group: "students" },
  { to: "/parent-management", label: "إدارة أولياء الأمور", roles: MANAGER_VP_COUNSELOR, icon: HeartHandshake, group: "students" },
  { to: "/warnings", label: "الإنذارات", roles: MANAGER_VP, icon: BellRing, group: "students" },
  { to: "/excuses", label: "الأعذار", roles: MANAGER_VP_COUNSELOR, icon: BookOpenCheck, group: "students" },
  { to: "/referrals", label: "الإحالات", roles: MANAGER_VP_COUNSELOR, icon: Send, group: "students" },
  { to: "/counselor", label: "الإرشاد", roles: MANAGER_VP_COUNSELOR, icon: HeartHandshake, group: "students" },
  { to: "/teacher/follow-ups", label: "طلبات المتابعة", roles: ["TEACHER"], icon: MessageSquareMore, group: "students" },
  { to: "/referrals/mine", label: "التحويلات", roles: ["TEACHER"], icon: Send, group: "students" },
  { to: "/attendance/monitoring", label: "متابعة التحضير", roles: MANAGER_VP, icon: BookOpenCheck, group: "operations" },
  { to: "/attendance/analytics", label: "الغياب والحضور", roles: MANAGER_VP, icon: BarChart3, group: "operations" },
  { to: "/attendance/absence-messages", label: "رسائل الغياب", roles: MANAGER_VP, icon: MessageSquareMore, group: "operations" },
  { to: "/morning", label: "التأخر الصباحي", roles: MANAGER_VP, capabilities: ["MORNING_ATTENDANCE"], icon: Sunrise, group: "operations" },
  { to: "/student-leaves", label: "الاستئذانات", roles: MANAGER_VP, icon: DoorOpen, group: "operations" },
  { to: "/gate", label: "بوابة المدرسة", roles: [...MANAGER_VP, "GATE_GUARD"], icon: DoorOpen, group: "operations" },
  { to: "/attendance/qr", label: "رموز QR", roles: ["SCHOOL_MANAGER"], icon: QrCode, group: "operations" },
  { to: "/devices", label: "أجهزة الحضور", roles: ["SCHOOL_MANAGER"], icon: Fingerprint, group: "operations" },
  { to: "/devices/roster-sync", label: "مزامنة أجهزة الطلاب", roles: ["SCHOOL_MANAGER"], icon: RefreshCw, group: "operations" },
  { to: "/staff", label: "الموظفون", roles: MANAGER_VP, icon: UsersRound, group: "management" },
  { to: "/academic-calendar", label: "التقويم الدراسي", roles: MANAGER_VP_COUNSELOR, icon: CalendarDays, group: "management" },
  { to: "/subscription", label: "الاشتراك", roles: ["SCHOOL_MANAGER"], icon: CreditCard, group: "management" },
  { to: "/settings", label: "الإعدادات", roles: ["SCHOOL_MANAGER"], icon: Settings, group: "management" },
];

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/workspace" className="group flex min-h-11 min-w-11 items-center gap-3" aria-label="الرئيسية — منصة المواظبة">
      <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-teal-400 to-teal-700 text-white shadow-md shadow-teal-950/20 transition-transform group-hover:-translate-y-0.5">
        <Building2 aria-hidden size={21} strokeWidth={2.3} />
      </span>
      {!compact && (
        <span className="min-w-0 leading-tight">
          <strong className="block truncate text-base font-bold text-white">منصة المواظبة</strong>
          <span className="mt-1 block text-[11px] font-medium text-teal-100/55">إدارة مدرسية أكثر وضوحًا</span>
        </span>
      )}
    </Link>
  );
}

function NavigationLinks({ items, schoolType, onNavigate, onLocked }: { items: NavigationItem[]; schoolType?: "BOYS" | "GIRLS"; onNavigate?: () => void; onLocked: (feature: SchoolFeature) => void }) {
  const features = useSchoolFeatures();
  const groups = (Object.keys(GROUP_LABELS) as NavigationGroup[]).filter((group) =>
    items.some((item) => item.group === group),
  );

  return <>{groups.map((group) => (
    <div key={group} className="mb-5 last:mb-0">
      <p className="mb-2 px-3 text-xs font-bold text-teal-100/70">{group === "students" ? `${studentPluralLabel(schoolType)} والمتابعة` : GROUP_LABELS[group]}</p>
      <div className="space-y-1">
        {items.filter((item) => item.group === group).map((item) => {
          const Icon = item.icon;
          const feature = featureForPath(item.to);
          if (feature && features?.[feature] === false) {
            return <button key={item.to} type="button" aria-disabled="true" aria-label={`${item.label} — يلزم اشتراك`} onClick={() => onLocked(feature)} className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 py-2.5 text-start text-[13px] text-slate-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-400">
              <Icon aria-hidden size={18} className="shrink-0 text-slate-500" />
              <span className="min-w-0"><span className="block">{item.label}</span><span className="mt-0.5 block text-[10px] text-amber-200/70">يلزم اشتراك</span></span>
            </button>;
          }
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/workspace"}
              onClick={onNavigate}
              className={({ isActive }) => `group relative flex min-h-11 items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-[color,background-color,box-shadow] duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-300 ${isActive ? "bg-teal-300/15 font-bold text-white shadow-sm ring-1 ring-teal-100/15 before:absolute before:inset-y-2 before:start-0 before:w-0.5 before:rounded-e-full before:bg-teal-300" : "text-slate-200 hover:bg-white/[0.06] hover:text-white"}`}
            >
              {({ isActive }) => (
                <>
                  <Icon aria-hidden size={18} className={`shrink-0 ${isActive ? "text-teal-200" : "text-teal-100/65 transition-colors group-hover:text-teal-200"}`} />
                  <span className="min-w-0">{item.to === "/students" ? studentPluralLabel(schoolType) : item.to === "/devices/roster-sync" ? `مزامنة أجهزة ${studentPluralLabel(schoolType)}` : item.label}</span>
                </>
              )}
            </NavLink>
          );
        })}
      </div>
    </div>
  ))}</>;
}

function AdditionalNavigation({ items, schoolType, onNavigate, onLocked }: { items: NavigationItem[]; schoolType?: "BOYS" | "GIRLS"; onNavigate?: () => void; onLocked: (feature: SchoolFeature) => void }) {
  if (items.length === 0) return null;
  const discoverablePaths = ["/warnings", "/excuses", "/referrals", "/attendance/analytics"];
  const preferredItems = discoverablePaths
    .map((path) => items.find((item) => item.to === path))
    .filter((item): item is NavigationItem => item !== undefined);
  const previewItems = [
    ...preferredItems,
    ...items.filter((item) => !preferredItems.some((preferred) => preferred.to === item.to)),
  ].slice(0, 3);
  const preview = previewItems
    .map((item) => item.to === "/students" ? studentPluralLabel(schoolType) : item.label)
    .join("، ");

  return (
    <details className="group rounded-xl border border-white/10 bg-white/[0.035]" data-testid="additional-navigation">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-xl px-3 py-3 text-slate-300 transition hover:bg-white/[0.06] hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-300">
        <span className="min-w-0">
          <span className="block text-[11px] font-bold text-teal-100/70">أدوات إضافية</span>
          <span className="mt-0.5 block text-sm font-bold">المتابعة وأدوات المدرسة</span>
          <span className="mt-1 block truncate text-[11px] font-medium text-slate-400" data-testid="additional-navigation-preview">
            {preview}{items.length > previewItems.length ? "، والمزيد" : ""}
          </span>
        </span>
        <ChevronDown aria-hidden size={17} className="shrink-0 transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-white/10 px-1 pt-4">
        <NavigationLinks items={items} schoolType={schoolType} onNavigate={onNavigate} onLocked={onLocked} />
      </div>
    </details>
  );
}

function UserPanel({ onLogout, onNavigate, mobile = false }: { onLogout: () => void; onNavigate?: () => void; mobile?: boolean }) {
  const me = useMe();
  if (!me.isSuccess) return null;
  return (
    <div className={`shrink-0 space-y-3 border-t p-4 ${mobile ? "border-slate-200" : "border-white/10 bg-[#0b211f]"}`}>
      <div className="flex min-w-0 items-center gap-3">
        <span className={`grid size-10 shrink-0 place-items-center rounded-full text-sm font-black ${mobile ? "bg-teal-50 text-teal-800" : "bg-white/10 text-teal-200"}`}>
          {me.data.name.trim().charAt(0)}
        </span>
        <div className="min-w-0 flex-1">
          <p title={me.data.name} className={`truncate text-sm font-bold ${mobile ? "text-slate-900" : "text-white"}`} data-testid={mobile ? "user-name-mobile" : "user-name"}>{me.data.name}</p>
          <p title={roleLabels(me.data.roles, me.data.active_school?.school_type)} className={`mt-1 truncate text-xs ${mobile ? "text-slate-600" : "text-slate-300"}`} data-testid={mobile ? "user-roles-mobile" : "user-roles"}>{roleLabels(me.data.roles, me.data.active_school?.school_type)}</p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <NavLink to="/account" onClick={onNavigate} className={({ isActive }) => `inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl border px-2 text-xs font-bold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 ${mobile ? `border-teal-200 text-teal-900 ${isActive ? "bg-teal-100" : "bg-teal-50 hover:bg-teal-100"}` : `border-teal-200/20 text-teal-100 focus-visible:outline-teal-300 ${isActive ? "bg-teal-300/20" : "bg-teal-300/10 hover:bg-teal-300/20"}`}`}>
          <UserRound aria-hidden size={16} className="shrink-0" />
          <span className="whitespace-nowrap">إدارة الحساب</span>
        </NavLink>
        <button type="button" onClick={onLogout} aria-label="تسجيل الخروج" className={`inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl px-2 text-xs font-bold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 ${mobile ? "text-slate-600 hover:bg-red-50 hover:text-red-700" : "text-slate-300 hover:bg-red-500/10 hover:text-red-200 focus-visible:outline-teal-300"}`}>
          <LogOut aria-hidden size={17} />
          <span className="whitespace-nowrap">تسجيل الخروج</span>
        </button>
      </div>
    </div>
  );
}

/** غلاف موحّد لكل شاشات المدرسة مع تنقل واضح ومتجاوب حسب الصلاحيات. */
export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const navigation = useNavigation();
  const me = useMe();
  const doLogout = useLogout();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const headerRef = useRef<HTMLElement>(null);
  const [headerHeight, setHeaderHeight] = useState(65);
  useEffect(() => {
    const header = headerRef.current;
    if (!header || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setHeaderHeight(header.getBoundingClientRect().height));
    observer.observe(header);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!mobileMenuOpen || typeof window.matchMedia !== "function") return;
    const desktop = window.matchMedia("(min-width: 1024px)");
    const closeOnDesktop = () => { if (desktop.matches) setMobileMenuOpen(false); };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, [mobileMenuOpen]);
  const [lockedFeature, setLockedFeature] = useState<SchoolFeature | null>(null);
  const showFeatureNotice = (feature: SchoolFeature) => { setMobileMenuOpen(false); setLockedFeature(feature); };
  const schoolType = me.data?.active_school?.school_type;
  const isManager = me.isSuccess && me.data.roles.includes("SCHOOL_MANAGER");
  const isVicePrincipalOnly = me.isSuccess && me.data.roles.includes("VICE_PRINCIPAL") && !isManager;
  const isCounselorWorkspace = me.isSuccess && me.data.roles.includes("COUNSELOR") && !isManager && !isVicePrincipalOnly;
  const authorizedItems = me.isSuccess ? NAVIGATION.filter((item) =>
    item.roles.some((role) => me.data.roles.includes(role)) ||
    (item.capabilities ?? []).some((capability) => (me.data.capabilities ?? []).includes(capability)),
  ) : [];
  const items = authorizedItems.map((item) =>
    isVicePrincipalOnly && item.to === "/dashboard"
      ? { ...item, label: "لوحة المتابعة" }
      : isCounselorWorkspace && item.to === "/counselor"
        ? { ...item, label: "لوحة الإرشاد", group: "overview" as const }
      : item,
  );
  const primaryPaths = isManager ? MANAGER_PRIMARY_PATHS : isVicePrincipalOnly ? VICE_PRINCIPAL_PRIMARY_PATHS : null;
  const primaryItems = primaryPaths ? items.filter((item) => primaryPaths.has(item.to)) : items;
  const additionalItems = primaryPaths ? items.filter((item) => !primaryPaths.has(item.to)) : [];
  const handleLogout = () => { void doLogout().then(() => navigate("/login", { replace: true })); };
  const drawerRef = useDialogA11y<HTMLElement>(mobileMenuOpen, () => setMobileMenuOpen(false));
  const currentItem = items.find((item) => item.to === location.pathname) ?? items.find((item) => item.to !== "/workspace" && location.pathname.startsWith(`${item.to}/`));
  const currentLabel = location.pathname === "/account" ? "إدارة الحساب" : currentItem?.to === "/students" ? studentPluralLabel(schoolType) : currentItem?.label ?? "مساحة العمل";
  const isNavigating = navigation.state !== "idle";

  return (
    <div className="min-h-dvh bg-[#f4f8f6] lg:flex">
      <a className="skip-link" href="#main-content">الانتقال إلى المحتوى</a>
      <aside className="hidden h-dvh w-70 shrink-0 flex-col overflow-hidden bg-[#102b28] lg:sticky lg:top-0 lg:flex">
        <div className="shrink-0 border-b border-white/[0.08] p-5"><Brand /></div>
        <nav aria-label="التنقل الرئيسي" className="sidebar-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-5">
          <NavigationLinks items={primaryItems} schoolType={schoolType} onLocked={showFeatureNotice} />
          <AdditionalNavigation items={additionalItems} schoolType={schoolType} onLocked={showFeatureNotice} />
        </nav>
        <UserPanel onLogout={handleLogout} />
      </aside>

      <div className="min-w-0 flex-1">
        <header ref={headerRef} className="app-shell-header sticky top-0 z-40 border-b border-[#dce8e4]/90 bg-[#fbfdfc]/95 px-3 py-2.5 shadow-[0_5px_20px_-18px_rgba(16,43,40,.42)] backdrop-blur-xl sm:px-4 sm:py-3 lg:px-8">
          {isNavigating && <div className="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-teal-100" role="progressbar" aria-label="جارٍ تحميل الصفحة" aria-valuetext="جارٍ تحميل الصفحة"><span className="block h-full w-2/5 animate-pulse bg-teal-700" /></div>}
          <div className="mx-auto flex max-w-7xl items-center gap-2.5 sm:gap-3">
            <div className="shrink-0 rounded-xl bg-[#102b28] p-1.5 lg:hidden"><Brand compact /></div>
            <div className="min-w-0 flex-1">
              <SchoolSwitcher />
              <nav aria-label="مسار الصفحة" className="mt-0.5 hidden items-center gap-1.5 text-xs text-slate-500 sm:flex">
                <Link to="/workspace" className="inline-flex min-h-8 min-w-8 items-center justify-center rounded-md font-medium hover:text-brand-800">الرئيسية</Link>
                <span aria-hidden>/</span>
                <span aria-current="page" className="truncate font-bold text-slate-700">{currentLabel}</span>
              </nav>
            </div>
            {me.data?.has_parent_portal && <SpaceSwitchButton destination="/parent">بوابة ولي الأمر</SpaceSwitchButton>}
            <button type="button" aria-label={mobileMenuOpen ? "إغلاق قائمة التنقل" : "فتح قائمة التنقل"} aria-expanded={mobileMenuOpen} aria-controls="mobile-navigation" className="grid size-11 shrink-0 place-items-center rounded-xl border border-[#dce8e4] bg-white text-slate-700 shadow-sm transition hover:border-teal-300 hover:text-teal-800 focus-visible:outline-2 lg:hidden" onClick={() => setMobileMenuOpen((open) => !open)}>
              {mobileMenuOpen ? <X aria-hidden size={20} /> : <Menu aria-hidden size={20} />}
            </button>
          </div>
        </header>

        {mobileMenuOpen && (
          <div className="fixed inset-0 z-30 bg-[#0b211f]/50 backdrop-blur-sm lg:hidden" style={{ paddingTop: headerHeight }} onClick={() => setMobileMenuOpen(false)}>
            <nav ref={drawerRef} id="mobile-navigation" role="dialog" aria-modal="true" aria-label="التنقل الرئيسي" tabIndex={-1} style={{ maxHeight: `calc(100dvh - ${headerHeight}px)` }} className="me-auto flex w-[min(88vw,22rem)] flex-col overflow-hidden border-e border-white/10 bg-[#102b28] shadow-2xl" onClick={(event) => event.stopPropagation()}>
              <div className="sidebar-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-5">
                <NavigationLinks items={primaryItems} schoolType={schoolType} onNavigate={() => setMobileMenuOpen(false)} onLocked={showFeatureNotice} />
                <AdditionalNavigation items={additionalItems} schoolType={schoolType} onNavigate={() => setMobileMenuOpen(false)} onLocked={showFeatureNotice} />
              </div>
              <div className="shrink-0 bg-[#fbfdfc]"><UserPanel onLogout={handleLogout} onNavigate={() => setMobileMenuOpen(false)} mobile /></div>
            </nav>
          </div>
        )}

        <main id="main-content" tabIndex={-1} aria-busy={isNavigating || undefined} className="mx-auto w-full max-w-[94rem] px-3 py-5 sm:px-6 sm:py-7 xl:px-8">
          <SchoolEmailVerificationNotice /><SchoolFeatureBoundary><Outlet /></SchoolFeatureBoundary>
        </main>
      </div>
      {lockedFeature && <Modal title="ميزة تتطلب اشتراكًا" onClose={() => setLockedFeature(null)}><FeatureSubscriptionNotice feature={lockedFeature} /></Modal>}
    </div>
  );
}
