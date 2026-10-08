import {
  Bell,
  BookOpenCheck,
  HeartHandshake,
  Home,
  LogOut,
  NotebookPen,
  UserRound,
} from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Button } from "@/components/Button";
import { useLogout, useMe } from "@/features/auth/useMe";
import { SpaceSwitchButton } from "@/features/parent/SpaceSwitchButton";

const links = [
  { to: "/parent", label: "أبنائي", Icon: Home },
  { to: "/parent/attendance", label: "المواظبة", Icon: BookOpenCheck },
  { to: "/parent/requests", label: "طلباتي", Icon: NotebookPen },
  { to: "/parent/notifications", label: "التنبيهات", Icon: Bell },
  { to: "/parent/account", label: "حسابي", Icon: UserRound },
];
export function ParentShell() {
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  return (
    <div className="min-h-dvh bg-[#f4f8f6]" data-testid="parent-shell">
      <a href="#parent-content" className="skip-link">
        الانتقال إلى المحتوى
      </a>
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-teal-800 text-white">
            <HeartHandshake aria-hidden size={22} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-base font-black">بوابة ولي الأمر</p>
            <p className="truncate text-xs text-slate-500">{me.data?.name}</p>
          </div>
          {(me.data?.memberships.length ?? 0) > 0 && (
            <SpaceSwitchButton
              destination={
                me.data?.active_school ? "/workspace" : "/select-school"
              }
            >
              مساحة العمل
            </SpaceSwitchButton>
          )}
          <Button
            variant="ghost"
            size="icon"
            aria-label="تسجيل الخروج"
            onClick={() =>
              void logout().then(() => navigate("/login", { replace: true }))
            }
          >
            <LogOut aria-hidden size={19} />
          </Button>
        </div>
      </header>
      <nav
        aria-label="تنقل بوابة ولي الأمر"
        className="sticky top-[69px] z-20 border-b border-slate-200 bg-white"
      >
        <div className="mx-auto grid max-w-6xl grid-cols-5 px-2">
          {links.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/parent"}
              className={({ isActive }) =>
                `flex min-h-14 flex-col items-center justify-center gap-1 border-b-2 px-1 py-2 text-xs font-bold sm:flex-row sm:gap-2 sm:text-sm ${isActive ? "border-teal-700 bg-teal-50 text-teal-900" : "border-transparent text-slate-500 hover:bg-slate-50"}`
              }
            >
              <Icon aria-hidden size={17} />
              {label}
            </NavLink>
          ))}
        </div>
      </nav>
      <main
        id="parent-content"
        className="mx-auto w-full max-w-6xl px-3 py-5 sm:px-6 sm:py-8"
        tabIndex={-1}
      >
        <Outlet />
      </main>
    </div>
  );
}
