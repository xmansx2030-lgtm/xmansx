import type { IScannerControls } from "@zxing/browser";
import { Camera, Flashlight, ImagePlus, LoaderCircle, RotateCcw, ScanLine, X } from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent } from "react";

/** يستخرج رمز الفصل من نص QR — يقبل الرابط الكامل أو الرمز الخام. */
export function extractQrToken(raw: string): string | null {
  const urlMatch = /\/qr\/([A-Za-z0-9_-]+)/.exec(raw);
  if (urlMatch) return urlMatch[1] ?? null;
  if (/^[A-Za-z0-9_-]{10,64}$/.test(raw)) return raw;
  return null;
}

interface QrScannerProps {
  onToken: (token: string) => void;
  onClose: () => void;
}

type ScannerStatus = "requesting" | "scanning" | "success" | "error";

function waitForCameraPreview(video: HTMLVideoElement): Promise<void> {
  if (video.readyState >= 2 && video.videoWidth > 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      cleanup();
      reject(new DOMException("Camera preview did not start", "NotReadableError"));
    }, 6_500);
    const onReady = () => {
      cleanup();
      resolve();
    };
    const cleanup = () => {
      window.clearTimeout(timeout);
      video.removeEventListener("loadeddata", onReady);
      video.removeEventListener("playing", onReady);
    };
    video.addEventListener("loadeddata", onReady, { once: true });
    video.addEventListener("playing", onReady, { once: true });
  });
}

function cameraErrorMessage(error: unknown): string {
  if (!window.isSecureContext) {
    return "تشغيل الكاميرا يحتاج رابطًا آمنًا HTTPS. افتح رابط المنصة الرسمي ثم حاول مجددًا.";
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    return "هذا المتصفح لا يتيح الوصول المباشر للكاميرا. استخدم التقاط صورة للرمز أو افتح المنصة في Safari أو Chrome المحدث.";
  }
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "إذن الكاميرا مرفوض. اسمح للمنصة باستخدام الكاميرا من إعدادات المتصفح ثم اضغط إعادة المحاولة.";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "لم يتم العثور على كاميرا في هذا الجهاز. يمكنك التقاط صورة للرمز أو اختيار الفصل يدويًا.";
  }
  if (name === "NotReadableError" || name === "AbortError" || name === "TrackStartError") {
    return "الكاميرا مستخدمة في تطبيق آخر أو تعذر تشغيلها. أغلق تطبيق الكاميرا ثم حاول مجددًا.";
  }
  return "تعذر تشغيل الكاميرا الآن. تحقق من الإذن والاتصال، أو استخدم التقاط صورة للرمز.";
}

/** ماسح QR متعدد المنصات عبر ZXing؛ يدعم Safari وChrome مع بديل التقاط صورة. */
export function QrScanner({ onToken, onClose }: QrScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const controlsRef = useRef<IScannerControls | null>(null);
  const deliveredRef = useRef(false);
  const onTokenRef = useRef(onToken);
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<ScannerStatus>("requesting");
  const [error, setError] = useState<string | null>(null);
  const [torchOn, setTorchOn] = useState(false);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [imageBusy, setImageBusy] = useState(false);

  useEffect(() => {
    onTokenRef.current = onToken;
  }, [onToken]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let cancelled = false;
    deliveredRef.current = false;

    const start = async () => {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        setError(cameraErrorMessage(null));
        setStatus("error");
        return;
      }
      try {
        const { BrowserQRCodeReader } = await import("@zxing/browser");
        const reader = new BrowserQRCodeReader(undefined, {
          delayBetweenScanAttempts: 250,
          delayBetweenScanSuccess: 750,
          tryPlayVideoTimeout: 7_000,
        });
        const controls = await reader.decodeFromConstraints(
          {
            audio: false,
            video: {
              facingMode: { ideal: "environment" },
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
          },
          video,
          (result, _decodeError, callbackControls) => {
            if (!result || deliveredRef.current) return;
            const token = extractQrToken(result.getText());
            if (!token) {
              setError("تمت قراءة رمز، لكنه ليس رمز فصل صالحًا لهذه المنصة.");
              return;
            }
            deliveredRef.current = true;
            callbackControls.stop();
            setStatus("success");
            onTokenRef.current(token);
          },
        );
        if (cancelled) {
          controls.stop();
          return;
        }
        controlsRef.current = controls;
        await waitForCameraPreview(video);
        if (cancelled) {
          controls.stop();
          return;
        }
        setTorchAvailable(typeof controls.switchTorch === "function");
        setStatus("scanning");
      } catch (cameraError) {
        if (cancelled) return;
        controlsRef.current?.stop();
        controlsRef.current = null;
        setError(cameraErrorMessage(cameraError));
        setStatus("error");
      }
    };

    void start();
    return () => {
      cancelled = true;
      controlsRef.current?.stop();
      controlsRef.current = null;
      const stream = video.srcObject;
      if (stream && "getTracks" in stream) stream.getTracks().forEach((track) => track.stop());
      video.srcObject = null;
    };
  }, [attempt]);

  const retry = () => {
    setStatus("requesting");
    setError(null);
    setTorchOn(false);
    setTorchAvailable(false);
    setAttempt((value) => value + 1);
  };

  const toggleTorch = async () => {
    const switchTorch = controlsRef.current?.switchTorch;
    if (!switchTorch) return;
    const next = !torchOn;
    try {
      await switchTorch(next);
      setTorchOn(next);
    } catch {
      setTorchAvailable(false);
      setError("الفلاش غير متاح مع الكاميرا الحالية، ويمكن متابعة المسح دون تشغيله.");
    }
  };

  const scanImage = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setImageBusy(true);
    setError(null);
    const objectUrl = URL.createObjectURL(file);
    try {
      const { BrowserQRCodeReader } = await import("@zxing/browser");
      const result = await new BrowserQRCodeReader().decodeFromImageUrl(objectUrl);
      const token = extractQrToken(result.getText());
      if (!token) {
        setError("الصورة واضحة، لكن الرمز ليس رمز فصل صالحًا لهذه المنصة.");
        return;
      }
      deliveredRef.current = true;
      controlsRef.current?.stop();
      setStatus("success");
      onTokenRef.current(token);
    } catch {
      setError("لم نتمكن من قراءة الرمز من الصورة. قرّب الكاميرا وتأكد من وضوح الرمز كاملًا.");
    } finally {
      URL.revokeObjectURL(objectUrl);
      setImageBusy(false);
    }
  };

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-slate-950 shadow-xl" data-testid="qr-scanner">
      <header className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-3 text-white">
        <div className="flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-xl bg-teal-400/15 text-teal-200"><ScanLine aria-hidden size={19} /></span>
          <div><h3 className="text-sm font-black">مسح رمز الفصل</h3><p className="text-[11px] text-slate-400">الكاميرا الخلفية تعمل تلقائيًا</p></div>
        </div>
        <button type="button" aria-label="إغلاق الماسح" onClick={onClose} className="grid size-9 place-items-center rounded-xl bg-white/5 text-slate-300 transition hover:bg-white/10 hover:text-white"><X aria-hidden size={18} /></button>
      </header>

      <div className="relative mx-auto aspect-[4/5] w-full max-w-md overflow-hidden bg-black sm:aspect-square">
        <video ref={videoRef} className="size-full object-cover" muted playsInline autoPlay data-testid="qr-video" />

        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(0,0,0,.32),rgba(0,0,0,.08),rgba(0,0,0,.32))]" />
        <div
          data-testid="qr-scan-frame"
          className="pointer-events-none absolute left-1/2 top-1/2 size-[68%] -translate-x-1/2 -translate-y-1/2 rounded-[1.75rem] border-2 border-white/90 shadow-[0_0_0_999px_rgba(0,0,0,.18),0_0_35px_rgba(45,212,191,.2)]"
        >
          <span className="absolute -start-0.5 -top-0.5 size-8 rounded-ss-[1.7rem] border-s-4 border-t-4 border-teal-300" />
          <span className="absolute -end-0.5 -top-0.5 size-8 rounded-se-[1.7rem] border-e-4 border-t-4 border-teal-300" />
          <span className="absolute -bottom-0.5 -start-0.5 size-8 rounded-es-[1.7rem] border-b-4 border-s-4 border-teal-300" />
          <span className="absolute -bottom-0.5 -end-0.5 size-8 rounded-ee-[1.7rem] border-b-4 border-e-4 border-teal-300" />
          {status === "scanning" && <span className="absolute inset-x-5 top-1/2 h-0.5 animate-pulse bg-gradient-to-r from-transparent via-teal-300 to-transparent shadow-[0_0_12px_rgba(94,234,212,.9)]" />}
        </div>

        {status === "requesting" && (
          <div className="absolute inset-0 grid place-items-center bg-slate-950/70 text-center text-white" role="status">
            <div><LoaderCircle aria-hidden size={30} className="mx-auto animate-spin text-teal-300" /><p className="mt-3 text-sm font-bold">جارٍ تشغيل الكاميرا...</p><p className="mt-1 text-xs text-slate-400">وافق على الإذن عند ظهوره</p></div>
          </div>
        )}
        {status === "error" && (
          <div className="absolute inset-0 grid place-items-center bg-slate-950/90 p-6 text-center text-white" role="alert">
            <div><Camera aria-hidden size={34} className="mx-auto text-amber-300" /><p className="mt-3 text-sm font-bold leading-7">{error}</p><button type="button" onClick={retry} className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-xl bg-white px-4 py-2 text-sm font-black text-slate-900"><RotateCcw aria-hidden size={16} /> إعادة المحاولة</button></div>
          </div>
        )}

        {torchAvailable && status === "scanning" && (
          <button type="button" aria-pressed={torchOn} onClick={() => void toggleTorch()} className={`absolute bottom-4 left-1/2 inline-flex -translate-x-1/2 items-center gap-2 rounded-full px-4 py-2 text-xs font-black shadow-lg backdrop-blur ${torchOn ? "bg-amber-300 text-slate-950" : "bg-slate-950/65 text-white ring-1 ring-white/20"}`}>
            <Flashlight aria-hidden size={16} /> {torchOn ? "إطفاء الفلاش" : "تشغيل الفلاش"}
          </button>
        )}
      </div>

      <div className="space-y-3 border-t border-white/10 bg-slate-950 px-4 py-4 text-center">
        <p className="text-xs leading-6 text-slate-300" aria-live="polite">
          {status === "scanning" ? "ضع الرمز كاملًا داخل الإطار وسيتم فتح الفصل تلقائيًا." : "يمكنك استخدام صورة محفوظة أو التقاط صورة جديدة للرمز."}
        </p>
        {error && status !== "error" && <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-xs font-bold text-amber-200" role="alert">{error}</p>}
        <label className="mx-auto inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-xl bg-white/10 px-4 py-2.5 text-sm font-black text-white ring-1 ring-white/15 transition hover:bg-white/15">
          {imageBusy ? <LoaderCircle aria-hidden size={17} className="animate-spin" /> : <ImagePlus aria-hidden size={17} />}
          {imageBusy ? "جارٍ قراءة الصورة..." : "التقاط صورة أو اختيارها"}
          <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(event) => void scanImage(event)} disabled={imageBusy} aria-label="التقاط صورة لرمز QR" />
        </label>
      </div>
    </section>
  );
}
