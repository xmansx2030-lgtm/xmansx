import { ApiError } from "@/api/client";
import { AlertCircle } from "lucide-react";

interface ErrorStateProps {
  error: unknown;
}

/** يعرض رسالة الخطأ العربية القادمة من الـ API، أو رسالة عامة — لا تفاصيل تقنية. */
export function ErrorState({ error }: ErrorStateProps) {
  const message = error instanceof ApiError ? error.message : "حدث خطأ غير متوقع.";
  const requestId = error instanceof ApiError ? error.requestId : null;

  return (
    <div role="alert" className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-red-100 text-red-700"><AlertCircle aria-hidden size={19} /></span>
      <div className="min-w-0">
      <p className="font-bold">تعذر إكمال الطلب</p>
      <p className="mt-1 leading-6">{message}</p>
      {requestId && (
        <details className="mt-2 text-xs text-slate-500">
          <summary className="w-fit cursor-pointer select-none font-medium hover:text-slate-700">
            معلومات الدعم
          </summary>
          <p className="mt-1" dir="ltr">
            رمز التتبع: <code className="select-all">{requestId}</code>
          </p>
        </details>
      )}
      </div>
    </div>
  );
}
