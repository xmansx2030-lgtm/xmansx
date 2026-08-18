import { ApiError } from "@/api/client";

interface ErrorStateProps {
  error: unknown;
}

/** يعرض رسالة الخطأ العربية القادمة من الـ API، أو رسالة عامة — لا تفاصيل تقنية. */
export function ErrorState({ error }: ErrorStateProps) {
  const message = error instanceof ApiError ? error.message : "حدث خطأ غير متوقع.";
  const requestId = error instanceof ApiError ? error.requestId : null;

  return (
    <span role="alert" className="text-red-700">
      {message}
      {requestId && <span className="ms-2 text-xs text-slate-400">({requestId})</span>}
    </span>
  );
}
