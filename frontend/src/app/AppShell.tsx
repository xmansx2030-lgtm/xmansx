import { Outlet } from "react-router-dom";

/** الهيكل العام: ترويسة + محتوى داخل حاوية Responsive — RTL افتراضيًا. */
export function AppShell() {
  return (
    <div className="min-h-dvh flex flex-col">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto w-full max-w-5xl px-4 py-3">
          <h1 className="text-lg font-bold text-slate-800">
            منصة المواظبة والمتابعة الطلابية
          </h1>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
