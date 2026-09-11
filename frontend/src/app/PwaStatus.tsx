import { RefreshCw, WifiOff, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useRegisterSW } from "virtual:pwa-register/react";

import { PwaInstallPrompt } from "@/app/PwaInstallPrompt";

export function PwaStatus() {
  const [online, setOnline] = useState(() => navigator.onLine);
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    offlineReady: [offlineReady, setOfflineReady],
    updateServiceWorker,
  } = useRegisterSW();

  useEffect(() => {
    const markOnline = () => setOnline(true);
    const markOffline = () => setOnline(false);
    window.addEventListener("online", markOnline);
    window.addEventListener("offline", markOffline);
    return () => {
      window.removeEventListener("online", markOnline);
      window.removeEventListener("offline", markOffline);
    };
  }, []);

  return (
    <>
      <PwaInstallPrompt />
      <div className="pointer-events-none fixed inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-50 flex flex-col items-center gap-2" aria-label="حالة التطبيق">
      {!online && (
        <div
          role="status"
          className="flex w-full max-w-lg items-center gap-2 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-950 shadow-lg"
        >
          <WifiOff aria-hidden size={18} className="shrink-0" />
          <span>تعذر الاتصال. لن تُعتمد أي عملية حتى يعود الاتصال.</span>
        </div>
      )}

      {needRefresh && (
        <div
          role="status"
          className="flex w-full max-w-lg flex-wrap items-center gap-3 rounded-2xl border border-blue-200 bg-white px-4 py-3 text-sm text-slate-800 shadow-lg"
        >
          <RefreshCw aria-hidden size={18} className="shrink-0 text-blue-700" />
          <span className="min-w-0 flex-1">يتوفر تحديث جديد للمنصة.</span>
          <button
            type="button"
            className="pointer-events-auto font-bold text-blue-700 hover:text-blue-900 focus-visible:outline-2 focus-visible:outline-offset-2"
            onClick={() => void updateServiceWorker(true)}
          >
            تحديث الآن
          </button>
          <button
            type="button"
            aria-label="تأجيل التحديث"
            title="تأجيل التحديث"
            className="pointer-events-auto grid size-11 place-items-center rounded-xl text-slate-500 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2"
            onClick={() => setNeedRefresh(false)}
          >
            <X aria-hidden size={18} />
          </button>
        </div>
      )}

      {offlineReady && !needRefresh && (
        <div
          role="status"
          className="flex w-full max-w-lg items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-950 shadow-lg"
        >
          <span className="min-w-0 flex-1">أصبحت واجهة المنصة جاهزة عند انقطاع الاتصال.</span>
          <button
            type="button"
            aria-label="إغلاق التنبيه"
            title="إغلاق التنبيه"
            className="pointer-events-auto grid size-11 place-items-center rounded-xl hover:bg-emerald-100 focus-visible:outline-2 focus-visible:outline-offset-2"
            onClick={() => setOfflineReady(false)}
          >
            <X aria-hidden size={18} />
          </button>
        </div>
      )}
      </div>
    </>
  );
}
