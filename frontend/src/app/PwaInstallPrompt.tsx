import {
  CheckCircle2,
  Download,
  PlusSquare,
  Share2,
  ShieldCheck,
  Sparkles,
  WifiOff,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/Button";

const DISMISS_UNTIL_KEY = "pwa-install-dismissed-until";
const DISMISS_FOR_MS = 14 * 24 * 60 * 60 * 1000;
const REVEAL_DELAY_MS = 1_200;

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

type InstallMode = "native" | "ios";

function isStandalone(): boolean {
  const navigatorWithStandalone = navigator as Navigator & { standalone?: boolean };
  return (
    navigatorWithStandalone.standalone === true ||
    window.matchMedia?.("(display-mode: standalone)").matches === true
  );
}

function isIosDevice(): boolean {
  return (
    /iPad|iPhone|iPod/i.test(navigator.userAgent) ||
    (/Macintosh/i.test(navigator.userAgent) && navigator.maxTouchPoints > 1)
  );
}

function isDismissed(): boolean {
  try {
    return Number(localStorage.getItem(DISMISS_UNTIL_KEY) ?? 0) > Date.now();
  } catch {
    return false;
  }
}

function isPreviewMode(): boolean {
  return import.meta.env.DEV && new URLSearchParams(window.location.search).has("pwa-install-preview");
}

/** رحلة تثبيت PWA مخصصة: Android/Chromium عبر prompt الأصلي وiOS عبر خطوات Safari. */
export function PwaInstallPrompt() {
  const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [mode, setMode] = useState<InstallMode | null>(null);
  const [open, setOpen] = useState(false);
  const [installing, setInstalling] = useState(false);
  const revealTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (isStandalone()) return;

    const preview = isPreviewMode();
    const reveal = (nextMode: InstallMode) => {
      if (!preview && isDismissed()) return;
      setMode(nextMode);
      if (revealTimer.current) clearTimeout(revealTimer.current);
      revealTimer.current = setTimeout(() => setOpen(true), REVEAL_DELAY_MS);
    };

    const onBeforeInstall = (event: Event) => {
      event.preventDefault();
      const promptEvent = event as BeforeInstallPromptEvent;
      setInstallEvent(promptEvent);
      reveal("native");
    };
    const onInstalled = () => {
      try {
        localStorage.removeItem(DISMISS_UNTIL_KEY);
      } catch {
        // بعض أوضاع الخصوصية تمنع التخزين؛ إخفاء النافذة يظل ممكنًا لهذه الجلسة.
      }
      setOpen(false);
      setInstallEvent(null);
    };

    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);

    if (isIosDevice()) reveal("ios");
    else if (preview) reveal("native");

    return () => {
      if (revealTimer.current) clearTimeout(revealTimer.current);
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const snooze = () => {
    try {
      localStorage.setItem(DISMISS_UNTIL_KEY, String(Date.now() + DISMISS_FOR_MS));
    } catch {
      // لا نحجب الإغلاق إذا كان التخزين المحلي غير متاح.
    }
    setOpen(false);
  };

  const install = async () => {
    if (!installEvent) {
      setOpen(false); // معاينة التطوير فقط؛ الإنتاج لا يصل هنا دون حدث المتصفح.
      return;
    }
    setInstalling(true);
    try {
      await installEvent.prompt();
      const choice = await installEvent.userChoice;
      if (choice.outcome === "dismissed") snooze();
      else setOpen(false);
      setInstallEvent(null);
    } finally {
      setInstalling(false);
    }
  };

  if (!open || !mode) return null;

  return (
    <div
      className="fixed inset-0 z-[90] flex items-end justify-center bg-slate-950/70 p-0 backdrop-blur-md sm:items-center sm:p-5"
      data-testid="pwa-install-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) snooze();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="pwa-install-title"
        aria-describedby="pwa-install-description"
        className="relative max-h-[94dvh] w-full overflow-y-auto rounded-t-[2rem] border border-white/15 bg-white shadow-[0_-24px_80px_rgba(7,27,25,0.35)] sm:max-w-lg sm:rounded-[2rem]"
      >
        <div className="relative overflow-hidden bg-gradient-to-br from-slate-950 via-teal-950 to-teal-800 px-6 pb-7 pt-6 text-white sm:px-8 sm:pb-8">
          <div className="absolute -end-16 -top-20 size-56 rounded-full bg-teal-300/15 blur-2xl" />
          <div className="absolute -bottom-20 -start-14 size-48 rounded-full bg-amber-300/10 blur-2xl" />
          <button
            type="button"
            aria-label="تذكيري لاحقًا"
            onClick={snooze}
            className="absolute end-4 top-4 z-10 grid size-10 place-items-center rounded-full bg-white/10 text-white/80 ring-1 ring-white/15 transition hover:bg-white/20 hover:text-white"
          >
            <X aria-hidden size={19} />
          </button>

          <div className="relative flex items-center gap-4 pe-10">
            <span className="grid size-16 shrink-0 place-items-center rounded-[1.35rem] bg-white p-2.5 shadow-2xl shadow-black/20 ring-1 ring-white/70">
              <img src="/icons/pwa-192.png" alt="" className="size-full rounded-xl" />
            </span>
            <div>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-black text-teal-100 ring-1 ring-white/10">
                <Sparkles aria-hidden size={13} /> تجربة أسرع وأسهل
              </span>
              <h2 id="pwa-install-title" className="mt-2 text-2xl font-black tracking-tight">
                ثبّت منصة المواظبة
              </h2>
            </div>
          </div>
          <p id="pwa-install-description" className="relative mt-4 max-w-md text-sm font-medium leading-7 text-teal-50/85">
            افتح التحضير والمتابعة من شاشتك الرئيسية كتطبيق مستقل، بسرعة أعلى ووصول مباشر أثناء اليوم الدراسي.
          </p>
        </div>

        <div className="space-y-5 p-6 sm:p-8">
          <div className="grid grid-cols-3 gap-2" aria-label="مزايا التطبيق">
            <Benefit icon={Download} label="دخول سريع" />
            <Benefit icon={WifiOff} label="واجهة دون اتصال" />
            <Benefit icon={ShieldCheck} label="آمن وخاص" />
          </div>

          {mode === "ios" ? (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4" data-testid="ios-install-steps">
              <p className="mb-3 text-sm font-black text-slate-900">على iPhone أو iPad:</p>
              <ol className="space-y-3 text-sm text-slate-700">
                <InstallStep number="1" icon={Share2}>اضغط زر المشاركة في Safari.</InstallStep>
                <InstallStep number="2" icon={PlusSquare}>اختر «إضافة إلى الشاشة الرئيسية».</InstallStep>
                <InstallStep number="3" icon={CheckCircle2}>اضغط «إضافة» وسيظهر التطبيق فورًا.</InstallStep>
              </ol>
            </div>
          ) : (
            <div className="rounded-2xl border border-teal-100 bg-teal-50/70 p-4 text-sm leading-6 text-teal-950">
              التثبيت خفيف ولا يحتاج متجر تطبيقات، ولن يغيّر بيانات الدخول أو صلاحيات حسابك.
            </div>
          )}

          <div className="flex flex-col gap-2 sm:flex-row">
            {mode === "native" ? (
              <Button className="min-h-12 flex-1 text-base" onClick={() => void install()} disabled={installing} data-testid="install-pwa">
                <Download aria-hidden size={19} /> {installing ? "جارٍ فتح التثبيت..." : "تثبيت التطبيق"}
              </Button>
            ) : (
              <Button className="min-h-12 flex-1 text-base" onClick={snooze}>فهمت، شكرًا</Button>
            )}
            <Button variant="secondary" className="min-h-12 sm:px-6" onClick={snooze}>
              لاحقًا
            </Button>
          </div>
          <p className="text-center text-[11px] leading-5 text-slate-400">لن نكرر هذا التنبيه قبل 14 يومًا إذا اخترت «لاحقًا».</p>
        </div>
      </section>
    </div>
  );
}

function Benefit({ icon: Icon, label }: { icon: typeof Download; label: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3 text-center shadow-sm">
      <Icon aria-hidden size={19} className="mx-auto text-teal-700" />
      <p className="mt-2 text-[11px] font-black text-slate-700">{label}</p>
    </div>
  );
}

function InstallStep({ number, icon: Icon, children }: { number: string; icon: typeof Share2; children: string }) {
  return (
    <li className="flex items-center gap-3">
      <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-white text-teal-700 shadow-sm ring-1 ring-slate-200"><Icon aria-hidden size={17} /></span>
      <span className="min-w-0 flex-1">{children}</span>
      <span className="text-xs font-black text-slate-400">{number}</span>
    </li>
  );
}
