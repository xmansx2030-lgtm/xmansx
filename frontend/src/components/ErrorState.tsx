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
        <details className="mt-2 text-xs text-slate-500">
          <summary className="w-fit cursor-pointer select-none font-medium hover:text-slate-700">
            معلومات الدعم
          </summary>
          <p className="mt-1" dir="ltr">
            رمز التتبع: <code className="select-all">{requestId}</code>
          </p>
        </details>
      )}
    </Alert>
  );
}
