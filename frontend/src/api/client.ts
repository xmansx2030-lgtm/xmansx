/** طبقة API المركزية — ممنوع fetch() مباشر داخل المكونات.
 *
 * - credentials: include (جلسات Cookies).
 * - أخطاء JSON موحدة {code, message, details} → ApiError.
 * - مهلة/إلغاء عبر AbortController.
 * - يقرأ X-Request-ID من الاستجابة لعرضه عند الأخطاء الداخلية.
 */

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const DEFAULT_TIMEOUT_MS = 15_000;

export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(status: number, body: ApiErrorBody, requestId: string | null) {
    super(body.message);
    this.name = "ApiError";
    this.code = body.code;
    this.status = status;
    this.details = body.details;
    this.requestId = requestId;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
}

/** قراءة cookie بالاسم — تستخدم لإرسال X-CSRFToken (الـ cookie ليست HttpOnly بتصميم Django). */
export function getCookie(name: string): string | null {
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as ApiErrorBody).code === "string" &&
    typeof (value as ApiErrorBody).message === "string"
  );
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const combinedSignal = signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal;

  const headers: Record<string, string> = {};
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (method !== "GET") {
    // CSRF لكل العمليات المعدلة — الجلسات Cookie-based
    const csrfToken = getCookie("csrftoken");
    if (csrfToken) {
      headers["X-CSRFToken"] = csrfToken;
    }
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      credentials: "include",
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: combinedSignal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError(
        0,
        { code: "TIMEOUT", message: "انتهت مهلة الاتصال بالخادم.", details: {} },
        null,
      );
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(
      0,
      { code: "NETWORK_ERROR", message: "تعذر الاتصال بالخادم، تحقق من اتصالك.", details: {} },
      null,
    );
  }

  const requestId = response.headers.get("X-Request-ID");

  if (!response.ok) {
    let errorBody: ApiErrorBody = {
      code: "API_ERROR",
      message: "تعذر تنفيذ الطلب.",
      details: {},
    };
    try {
      const parsed: unknown = await response.json();
      if (isApiErrorBody(parsed)) {
        errorBody = { code: parsed.code, message: parsed.message, details: parsed.details ?? {} };
      }
    } catch {
      // استجابة غير JSON — نبقي الرسالة العامة
    }
    throw new ApiError(response.status, errorBody, requestId);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
