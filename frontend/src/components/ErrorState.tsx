import { ApiError } from "@/api/client";
import { Alert } from "@/components/Alert";

interface ErrorStateProps {
  error: unknown;
}

/** يعرض رسالة الخطأ العربية القادمة من الـ API، أو رسالة عامة — لا تفاصيل تقنية. */
export function ErrorState({ error }: ErrorStateProps) {
  const message = error instanceof ApiError ? error.message : "حدث خطأ غير متوقع.";
  const requestId = error instanceof ApiError ? error.requestId : null;

  return (
    <Alert tone="danger" title="تعذر إكمال الطلب">
      <p>{message}</p>
      {requestId && (
        <details className="mt-3 rounded-xl border border-rose-200/70 bg-white/65 p-3 text-xs text-slate-600">
          <summary className="w-fit cursor-pointer select-none rounded-lg px-2 font-bold text-rose-900 hover:bg-rose-100/70">
            معلومات الدعم
          </summary>
          <p className="mt-2 rounded-lg bg-rose-50 px-3 py-2" dir="ltr">
            رمز التتبع: <code className="select-all">{requestId}</code>
          </p>
        </details>
      )}
    </Alert>
  );
}
