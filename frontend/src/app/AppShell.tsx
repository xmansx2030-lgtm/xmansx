import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/Button";
import { SchoolSwitcher } from "@/features/auth/SchoolSwitcher";
import { useLogout, useMe } from "@/features/auth/useMe";
import { roleLabels } from "@/utils/roles";

const SETTINGS_ROLES = ["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR"];
const STUDENTS_ROLES = ["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR"];
const STAFF_ROLES = ["SCHOOL_MANAGER", "VICE_PRINCIPAL"];
const EXCUSES_ROLES = ["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR"];
const REFERRALS_ROLES = ["SCHOOL_MANAGER", "VICE_PRINCIPAL", "COUNSELOR"];

/** الهيكل العام بعد اختيار المدرسة: المستخدم، المدرسة الحالية، الأدوار، التبديل، الخروج. */
export function AppShell() {
  const navigate = useNavigate();
  const me = useMe();
  const doLogout = useLogout();

  return (
    <div className="min-h-dvh flex flex-col bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-bold text-slate-800">منصة المواظبة</h1>
            <SchoolSwitcher />
            {me.isSuccess && me.data.roles.some((r) => STUDENTS_ROLES.includes(r)) && (
              <NavLink
                to="/students"
                className={({ isActive }) =>
                  `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                }
              >
                الطلاب
              </NavLink>
            )}
            {me.isSuccess && me.data.roles.some((r) => STAFF_ROLES.includes(r)) && (
              <NavLink
                to="/staff"
                className={({ isActive }) =>
                  `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                }
              >
                الموظفون
              </NavLink>
            )}
            {me.isSuccess &&
              me.data.roles.some((r) => ["SCHOOL_MANAGER", "VICE_PRINCIPAL"].includes(r)) && (
                <>
                  <NavLink
                    to="/attendance/monitoring"
                    className={({ isActive }) =>
                      `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                    }
                  >
                    متابعة التحضير
                  </NavLink>
                  <NavLink
                    to="/attendance/analytics"
                    className={({ isActive }) =>
                      `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                    }
                  >
                    الغياب والحضور
                  </NavLink>
                </>
              )}
            {me.isSuccess && me.data.roles.some((r) => EXCUSES_ROLES.includes(r)) && (
              <NavLink
                to="/excuses"
                className={({ isActive }) =>
                  `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                }
              >
                الأعذار
              </NavLink>
            )}
            {me.isSuccess && me.data.roles.some((r) => REFERRALS_ROLES.includes(r)) && (
              <NavLink
                to="/referrals"
                className={({ isActive }) =>
                  `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                }
              >
                الإحالات
              </NavLink>
            )}
            {me.isSuccess && me.data.roles.includes("TEACHER") && (
              <NavLink
                to="/referrals/mine"
                className={({ isActive }) =>
                  `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                }
              >
                إحالاتي
              </NavLink>
            )}
            {me.isSuccess && me.data.roles.includes("SCHOOL_MANAGER") && (
              <NavLink
                to="/attendance/qr"
                className={({ isActive }) =>
                  `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                }
              >
                رموز QR
              </NavLink>
            )}
            {me.isSuccess &&
              me.data.roles.some((r) => ["SCHOOL_MANAGER", "VICE_PRINCIPAL"].includes(r)) && (
                <>
                  <NavLink
                    to="/morning"
                    className={({ isActive }) =>
                      `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                    }
                  >
                    الحضور الصباحي
                  </NavLink>
                  <NavLink
                    to="/warnings"
                    className={({ isActive }) =>
                      `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                    }
                  >
                    الإنذارات
                  </NavLink>
                </>
              )}
            {me.isSuccess && me.data.roles.includes("SCHOOL_MANAGER") && (
              <NavLink
                to="/devices"
                className={({ isActive }) =>
                  `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                }
              >
                أجهزة الحضور
              </NavLink>
            )}
            {me.isSuccess && me.data.roles.some((role) => role === "SCHOOL_MANAGER" || role === "VICE_PRINCIPAL") && (
              <NavLink
                to="/devices/roster-sync"
                className={({ isActive }) =>
                  `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                }
              >
                أجهزة الطلاب
              </NavLink>
            )}
            {me.isSuccess && me.data.roles.some((r) => SETTINGS_ROLES.includes(r)) && (
              <NavLink
                to="/settings"
                className={({ isActive }) =>
                  `text-sm font-medium ${isActive ? "text-blue-700" : "text-slate-500 hover:text-slate-800"}`
                }
              >
                الإعدادات
              </NavLink>
            )}
          </div>
          <div className="flex items-center gap-3">
            {me.isSuccess && (
              <div className="text-end">
                <p className="text-sm font-medium text-slate-800" data-testid="user-name">
                  {me.data.name}
                </p>
                <p className="text-xs text-slate-500" data-testid="user-roles">
                  {roleLabels(me.data.roles)}
                </p>
              </div>
            )}
            <Button
              variant="secondary"
              onClick={() => {
                void doLogout().then(() => navigate("/login", { replace: true }));
              }}
            >
              تسجيل الخروج
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
