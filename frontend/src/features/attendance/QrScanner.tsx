import { useEffect, useRef, useState } from "react";

/** واجهة BarcodeDetector غير المضمنة في تعريفات TS بعد. */
interface DetectedBarcode {
  rawValue: string;
}
interface BarcodeDetectorLike {
  detect(source: CanvasImageSource): Promise<DetectedBarcode[]>;
}
type BarcodeDetectorCtor = new (options?: { formats: string[] }) => BarcodeDetectorLike;

function getBarcodeDetector(): BarcodeDetectorCtor | null {
  const ctor = (globalThis as { BarcodeDetector?: BarcodeDetectorCtor }).BarcodeDetector;
  return ctor ?? null;
}

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

/** ماسح QR داخل التطبيق عبر BarcodeDetector — مع بديل واضح عند عدم الدعم.
 *  الرمز لا يمنح أي صلاحية: الخادم يتحقق من الجلسة والعضوية والدور دائمًا. */
export function QrScanner({ onToken, onClose }: QrScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const supported = getBarcodeDetector() !== null;

  useEffect(() => {
    if (!supported) return;
    const Detector = getBarcodeDetector();
    if (!Detector || !videoRef.current) return;

    let stream: MediaStream | null = null;
    let timer: ReturnType<typeof setInterval> | null = null;
    let stopped = false;
    const video = videoRef.current;

    const detector = new Detector({ formats: ["qr_code"] });
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" } })
      .then((mediaStream) => {
        if (stopped) {
          mediaStream.getTracks().forEach((t) => t.stop());
          return;
        }
        stream = mediaStream;
        video.srcObject = mediaStream;
        void video.play();
        timer = setInterval(() => {
          void detector
            .detect(video)
            .then((codes) => {
              const token = codes.map((c) => extractQrToken(c.rawValue)).find(Boolean);
              if (token) {
                onToken(token);
              }
            })
            .catch(() => undefined); // إطار غير جاهز — نتجاهل ونعيد المحاولة
        }, 500);
      })
      .catch(() => {
        setError("تعذر فتح الكاميرا — تحقق من الإذن أو اختر الفصل يدويًا.");
      });

    return () => {
      stopped = true;
      if (timer) clearInterval(timer);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [supported, onToken]);

  if (!supported) {
    return (
      <div
        className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
        data-testid="qr-unsupported"
      >
        المتصفح لا يدعم المسح داخل التطبيق. امسح الملصق بكاميرا الجهاز مباشرة (الرمز رابط يفتح
        الفصل)، أو اختر الفصل يدويًا من القائمة.
        <button type="button" className="ms-2 font-medium underline" onClick={onClose}>
          إغلاق
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {error ? (
        <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {error}
        </p>
      ) : (
        <video
          ref={videoRef}
          className="aspect-square w-full max-w-xs rounded-lg bg-slate-900 object-cover"
          muted
          playsInline
          data-testid="qr-video"
        />
      )}
    </div>
  );
}
