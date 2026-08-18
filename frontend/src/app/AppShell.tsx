import { Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/Button";
import { SchoolSwitcher } from "@/features/auth/SchoolSwitcher";
import { useLogout, useMe } from "@/features/auth/useMe";
import { roleLabels } from "@/utils/roles";

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
