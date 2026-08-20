import { LogOut, Menu, X } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/Button";
import { SchoolSwitcher } from "@/features/auth/SchoolSwitcher";
import { useLogout, useMe } from "@/features/auth/useMe";
import { roleLabels } from "@/utils/roles";

type Role = "SCHOOL_MANAGER" | "VICE_PRINCIPAL" | "COUNSELOR" | "TEACHER";

interface NavigationItem {
  to: string;
  label: string;
  roles: Role[];
}

const MANAGER_VP: Role[] = ["SCHOOL_MANAGER", "VICE_PRINCIPAL"];
const MANAGER_VP_COUNSELOR: Role[] = [...MANAGER_VP, "COUNSELOR"];

const NAVIGATION: NavigationItem[] = [
  { to: "/dashboard", label: "لوحة الإدارة", roles: MANAGER_VP },
  { to: "/students", label: "الطلاب", roles: MANAGER_VP_COUNSELOR },
  { to: "/staff", label: "الموظفون", roles: MANAGER_VP },
  { to: "/attendance/monitoring", label: "متابعة التحضير", roles: MANAGER_VP },
  { to: "/attendance/analytics", label: "الغياب والحضور", roles: MANAGER_VP },
  { to: "/excuses", label: "الأعذار", roles: MANAGER_VP_COUNSELOR },
  { to: "/referrals", label: "الإحالات", roles: MANAGER_VP_COUNSELOR },
  { to: "/counselor", label: "الإرشاد", roles: MANAGER_VP_COUNSELOR },
  { to: "/teacher/follow-ups", label: "طلبات المتابعة", roles: ["TEACHER"] },
  { to: "/referrals/mine", label: "إحالاتي", roles: ["TEACHER"] },
  { to: "/attendance/qr", label: "رموز QR", roles: ["SCHOOL_MANAGER"] },
  { to: "/morning", label: "الحضور الصباحي", roles: MANAGER_VP },
  { to: "/warnings", label: "الإنذارات", roles: MANAGER_VP },
  { to: "/devices", label: "أجهزة الحضور", roles: ["SCHOOL_MANAGER"] },
  { to: "/subscription", label: "الاشتراك", roles: ["SCHOOL_MANAGER"] },
  { to: "/devices/roster-sync", label: "أجهزة الطلاب", roles: MANAGER_VP },
  { to: "/settings", label: "الإعدادات", roles: MANAGER_VP_COUNSELOR },
];

function NavigationLinks({
  items,
  mobile = false,
  onNavigate,
}: {
  items: NavigationItem[];
  mobile?: boolean;
  onNavigate?: () => void;
}) {
  return items.map((item) => (
    <NavLink
      key={item.to}
      to={item.to}
      onClick={onNavigate}
      className={({ isActive }) =>
        `${mobile ? "rounded-lg px-3 py-2" : "shrink-0 border-b-2 px-1 py-3"} text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 ${
          isActive
            ? mobile
              ? "bg-blue-50 text-blue-800"
              : "border-blue-700 text-blue-800"
            : mobile
              ? "text-slate-700 hover:bg-slate-100"
              : "border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900"
        }`
      }
    >
      {item.label}
    </NavLink>
  ));
}

/** Responsive shell with role-scoped navigation and explicit auth-boundary cache clearing. */
export function AppShell() {
  const navigate = useNavigate();
  const me = useMe();
  const doLogout = useLogout();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const items = me.isSuccess
    ? NAVIGATION.filter((item) => item.roles.some((role) => me.data.roles.includes(role)))
    : [];

  const handleLogout = () => {
    void doLogout().then(() => navigate("/login", { replace: true }));
  };

  return (
    <div className="flex min-h-dvh flex-col bg-slate-50">
      <a className="skip-link" href="#main-content">
        الانتقال إلى المحتوى
      </a>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-7xl items-center gap-3 px-4 py-3">
          <Link to="/" className="shrink-0 text-base font-black text-slate-900 sm:text-lg">
            منصة المواظبة
          </Link>
          <div className="min-w-0 flex-1">
            <SchoolSwitcher />
          </div>

          {me.isSuccess && (
            <div className="hidden shrink-0 items-center gap-3 xl:flex">
              <div className="text-end">
                <p className="text-sm font-medium text-slate-800" data-testid="user-name">
                  {me.data.name}
                </p>
                <p className="text-xs text-slate-500" data-testid="user-roles">
                  {roleLabels(me.data.roles)}
                </p>
              </div>
              <Button variant="secondary" onClick={handleLogout}>
                <LogOut aria-hidden size={17} />
                تسجيل الخروج
              </Button>
            </div>
          )}

          <button
            type="button"
            aria-label={mobileMenuOpen ? "إغلاق قائمة التنقل" : "فتح قائمة التنقل"}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-navigation"
            title={mobileMenuOpen ? "إغلاق القائمة" : "فتح القائمة"}
            className="grid size-10 shrink-0 place-items-center rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 xl:hidden"
            onClick={() => setMobileMenuOpen((open) => !open)}
          >
            {mobileMenuOpen ? <X aria-hidden size={20} /> : <Menu aria-hidden size={20} />}
          </button>
        </div>

        {items.length > 0 && (
          <nav
            aria-label="التنقل الرئيسي"
            className="mx-auto hidden w-full max-w-7xl flex-wrap justify-center gap-x-5 px-4 xl:flex"
          >
            <NavigationLinks items={items} />
          </nav>
        )}

        {mobileMenuOpen && (
          <nav
            id="mobile-navigation"
            aria-label="التنقل الرئيسي"
            className="max-h-[min(65dvh,34rem)] overflow-y-auto border-t border-slate-200 px-4 py-3 xl:hidden"
          >
            <div className="grid grid-cols-2 gap-1">
              <NavigationLinks
                items={items}
                mobile
                onNavigate={() => setMobileMenuOpen(false)}
              />
            </div>
            {me.isSuccess && (
              <div className="mt-3 flex items-center justify-between gap-3 border-t border-slate-200 pt-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-800" data-testid="user-name-mobile">
                    {me.data.name}
                  </p>
                  <p className="truncate text-xs text-slate-500" data-testid="user-roles-mobile">
                    {roleLabels(me.data.roles)}
                  </p>
                </div>
                <Button variant="secondary" onClick={handleLogout} className="shrink-0">
                  <LogOut aria-hidden size={17} />
                  خروج
                </Button>
              </div>
            )}
          </nav>
        )}
      </header>
      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto w-full max-w-7xl flex-1 px-4 py-5 sm:py-6"
      >
        <Outlet />
      </main>
    </div>
  );
}
